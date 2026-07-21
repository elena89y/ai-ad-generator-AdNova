"""FMT-QUAL — 포맷(상세/카드/배너) 조판 품질 베이스라인 러너 — 담당: 한의정. (v6 T3 후속)

배경: 지금까지 모든 통제 실험은 히어로 1장(poster=False)만 측정 — 상세/카드/배너 조판 품질은
미측정 공백. 본 러너가 **생산 경로 그대로**(run_from_upload_v2 → _render_multiformat) 포맷
산출물을 통제 생성하고, 조판 품질을 정량 캡처한다.

측정 축:
  - 컷 다양성(핵심): _render_multiformat 가 이미 찍는 `corr=` 로그를 핸들러로 캡처
    (생산 코드의 자체 계측 재사용, 드리프트 0). 채택된 컷의 상관계수 median/max,
    임계(0.84) 초과=would-reject 수, 폴백(예산소진·전변형유사 강제채택) 횟수.
  - 신뢰성: 성공/실패, 생성 시간.
  - 육안 정본: 산출물을 results/ai/fmtqual/{입력}/{포맷}/ 에 저장 → 아트디렉터 판정.

기본 포맷 = detail + banner (효율): detail=컷다양성+롱스크롤 조판, banner=CPU 타이포(무료).
cardnews 는 detail 과 동일한 컷 생성 로직이라 다양성 축은 중복 → 필요 시 --formats 로 추가.

⚠️ GPU 실행: 배치가 Kontext 를 in-process 로드 → 운영 워커와 VRAM 경쟁(OOM). HYB 패턴대로
   워커 pause → 실행 → restore. 예산: detail ~561s/입력(4컷 Kontext). 6입력 ≈ 56분.

사용(VM, backend/에서):
  # 드라이런(생성·GPU 없이 배선·매니페스트·텔레메트리 정규식 검증):
  ../.venv/bin/python scripts/fmtqual_baseline.py run --dry-run --inputs-dir ~/HOLDOUT_inputs
  # 실측(워커 pause 상태에서):
  ../.venv/bin/python scripts/fmtqual_baseline.py run --inputs-dir ~/HOLDOUT_inputs --formats detail,banner
  ../.venv/bin/python scripts/fmtqual_baseline.py summary
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import sys
import time
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")  # 키는 backend/.env (VM) — 호출자 env 의존 금지(HYB 사고 계승)

from app.harness.run_logger import RunLogger  # noqa: E402

logger = logging.getLogger("fmtqual")

MANIFEST = BACKEND / "experiments" / "holdout001_inputs.yaml"
RUNS_REAL = BACKEND / "experiments" / "runs.jsonl"
RUNS_DRY = BACKEND / "results" / "ai" / "fmtqual_dryrun_runs.jsonl"
SUMMARY = BACKEND / "experiments" / "fmtqual_summary.md"
SUMMARY_DRY = BACKEND / "results" / "ai" / "fmtqual_dryrun_summary.md"
OUT_ROOT = BACKEND / "results" / "ai" / "fmtqual"
GATE = 0.84  # MAX_STRUCTURE_CORRELATION (similarity.py) — would-reject 판정 기준

FORMATS = ("detail", "cardnews", "banner")
_HEAVY = {"detail", "cardnews"}  # GPU 4컷 재시도 경로

# _generate_with_retry 로그 문면(generation_app.py:157·170·172·174). corr= 값 추출 +
#   '채택'만 집계(재시도 거부 라인 제외). 폴백 = 예산소진/전변형유사 강제채택.
_CORR_RE = re.compile(r"corr=([0-9.]+)")
_ACCEPT_MARK = ("충분히 다름", "가장 덜 유사한 결과", "최저상관 결과")
_FALLBACK_MARK = ("가장 덜 유사한 결과", "최저상관 결과")


class _CutTelemetry(logging.Handler):
    """generation_app 로거에 붙여 컷 채택 corr·폴백을 캡처(생산 계측 재사용)."""

    def __init__(self) -> None:
        super().__init__()
        self.corrs: list[float] = []
        self.fallbacks = 0

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return
        m = _CORR_RE.search(msg)
        if not m or not any(k in msg for k in _ACCEPT_MARK):
            return  # corr 없거나 '채택' 라인 아님(재시도 거부는 스킵)
        self.corrs.append(float(m.group(1)))
        if any(k in msg for k in _FALLBACK_MARK):
            self.fallbacks += 1


def _load_manifest() -> dict:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert data.get("items"), "매니페스트 items 비어 있음"
    return data


def _render_banner(hero_out, name: str, work_dir: Path) -> list[str]:
    """배너 = CPU 조판(히어로 재사용, 4컷 생성 없음). generate_v5 BANNER 경로."""
    from app.schemas.ads import AdPurpose
    from app.services import pipeline_v5
    from app.services.pipeline_v5.hero import hero_from_existing

    source = getattr(hero_out, "image_without_typography_path", None) or hero_out.final_image_path
    head, _, sub = hero_out.copy_text.partition("\n")
    style = getattr(hero_out.style, "value", hero_out.style) if hero_out.style else None
    try:
        h = hero_from_existing(
            source, product_name=name, headline=head.strip() or name,
            subcopy=sub.strip(), domain=getattr(hero_out, "domain", "food"), style=style)
    except TypeError:  # detail_cuts 가 필수인 시그니처면 빈 튜플로
        h = hero_from_existing(
            source, product_name=name, headline=head.strip() or name,
            subcopy=sub.strip(), detail_cuts=(), domain=getattr(hero_out, "domain", "food"),
            style=style)
    r = pipeline_v5.generate_v5(source, name, purpose=AdPurpose.BANNER,
                                hero_asset=h, output_dir=str(work_dir))
    return list(r.outputs)


def _run_one_format(hero_out, item: dict, fmt: str, runs_path: Path,
                    save_dir: Path) -> None:
    from app import generation_app as ga
    from app.schemas.ads import AdPurpose

    purpose = {"detail": AdPurpose.DETAIL_PAGE, "cardnews": AdPurpose.CARD_NEWS,
               "banner": AdPurpose.BANNER}[fmt]
    tele = _CutTelemetry()
    ga_logger = logging.getLogger("app.generation_app")
    ga_logger.addHandler(tele)
    try:
        with RunLogger(phase="FMT-QUAL", mode=item["expected_mode"],
                       engine=f"format:{fmt}", input=item["file"],
                       params={"format": fmt, "product": item["name"]},
                       runs_path=runs_path) as run:
            run.set_meta(gpu_used=fmt in _HEAVY)
            t0 = time.monotonic()
            if fmt in _HEAVY:
                resp = ga._render_multiformat(hero_out, item["name"], purpose)
                outputs = list(getattr(resp, "format_outputs", None) or [])
            else:
                outputs = _render_banner(hero_out, item["name"], save_dir / "_work")
            dt = round(time.monotonic() - t0, 1)
            run.add_metrics({
                "gen_s": dt,
                "cut_corr_median": (round(statistics.median(tele.corrs), 4)
                                    if tele.corrs else None),
                "cut_corr_max": round(max(tele.corrs), 4) if tele.corrs else None,
                "cuts_would_reject": sum(1 for c in tele.corrs if c >= GATE),
                "cut_fallbacks": tele.fallbacks,
                "n_cuts_measured": len(tele.corrs),
                "n_outputs": len(outputs),
            })
            _persist_outputs(outputs, save_dir, fmt)
            run.set_output(outputs[0] if outputs else str(save_dir))
            logger.info("[%s] %s: %ss corr_med=%s reject=%d/%d fallback=%d out=%d",
                        fmt, item["file"], dt,
                        round(statistics.median(tele.corrs), 3) if tele.corrs else "—",
                        sum(1 for c in tele.corrs if c >= GATE), len(tele.corrs),
                        tele.fallbacks, len(outputs))
    finally:
        ga_logger.removeHandler(tele)


def _persist_outputs(outputs: list[str], save_dir: Path, fmt: str) -> None:
    """육안 정본용 — 산출물을 fmtqual/{입력}/{포맷}/ 로 복사."""
    import shutil

    dst = save_dir / fmt
    dst.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(outputs, 1):
        src = Path(p)
        # generation_app 은 /result/{name} URL 로 주기도 함 → RESULTS_DIR 실경로로 변환
        if not src.exists():
            from app.services import image_service
            src = image_service.RESULTS_DIR / src.name
        if src.exists():
            shutil.copy(src, dst / f"{fmt}_{i:02d}{src.suffix}")


def cmd_run(args: argparse.Namespace) -> None:
    data = _load_manifest()
    seed = int(data.get("seed", 1234))
    inputs_dir = Path(args.inputs_dir).expanduser()
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    assert all(f in FORMATS for f in formats), f"미지 포맷: {formats} (허용 {FORMATS})"
    items = data["items"]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        items = [i for i in items if i["file"] in wanted]
    if args.sample:  # 모드별 앞 N개(3모드 균형 커버) — ascii 인자라 중첩 셸 안전
        seen: dict = {}
        picked = []
        for i in items:
            m = i["expected_mode"]
            if seen.get(m, 0) < args.sample:
                picked.append(i)
                seen[m] = seen.get(m, 0) + 1
        items = picked
    if args.limit:
        items = items[: args.limit]

    logger.info("FMT-QUAL run: %d입력 × %s (style=%s, seed=%d)%s",
                len(items), formats, args.style, seed, " [DRY]" if args.dry_run else "")
    if args.dry_run:
        _dry_validate(items, inputs_dir, formats)
        return

    from app.schemas.ads import ProductInfo, StylePreset
    from app.services.generation_service import run_from_upload_v2

    style = StylePreset(args.style)
    for item in items:
        image_path = inputs_dir / item["file"]
        if not image_path.exists():
            logger.error("입력 없음: %s", image_path)
            continue
        save_dir = OUT_ROOT / Path(item["file"]).stem
        try:
            hero_out = run_from_upload_v2(
                str(image_path), ProductInfo(name=item["name"]), style,
                seed=seed, use_vision=False, poster=False)
        except Exception:  # noqa: BLE001 — 히어로 실패 시 그 입력만 스킵
            logger.exception("[hero] %s 실패", item["file"])
            continue
        for fmt in formats:
            try:
                _run_one_format(hero_out, item, fmt, runs_path, save_dir)
            except Exception:  # noqa: BLE001 — 1포맷 실패가 배치를 죽이면 안 됨(원장 error 행)
                logger.exception("[%s] %s 실패", fmt, item["file"])


def _dry_validate(items: list, inputs_dir: Path, formats: list) -> None:
    """생성·GPU 없이: 입력 존재·텔레메트리 정규식·포맷 매핑만 검증."""
    missing = [i["file"] for i in items if not (inputs_dir / i["file"]).exists()]
    print(f"입력 {len(items)}건, 누락 {missing or '없음'}")
    tele = _CutTelemetry()
    samples = [
        "TOP_VIEW variant=75: 기존 컷들과 충분히 다름(corr=0.812)",       # 채택
        "TOP_VIEW variant=90: 기존 컷과 여전히 유사(corr=0.951) → 다음 재시도",  # 스킵
        "LIFESTYLE 전 변형([0, 30])이 기존 컷과 유사 — 가장 덜 유사한 결과(corr=0.933)로 진행",  # 폴백
        "TEXTURE_CLOSEUP: 시간 예산 소진 — 남은 변형 생략, 최저상관 결과(corr=0.907) 채택",  # 폴백
    ]
    for s in samples:
        tele.emit(logging.LogRecord("app.generation_app", logging.INFO, "", 0, s, None, None))
    assert tele.corrs == [0.812, 0.933, 0.907], f"정규식 캡처 오류: {tele.corrs}"
    assert tele.fallbacks == 2, f"폴백 집계 오류: {tele.fallbacks}"
    print(f"텔레메트리 검증 OK: corrs={tele.corrs} fallbacks={tele.fallbacks}")
    print(f"포맷 {formats} → heavy(GPU)={[f for f in formats if f in _HEAVY]}, "
          f"cpu={[f for f in formats if f not in _HEAVY]}")


def cmd_summary(args: argparse.Namespace) -> None:
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    if not runs_path.is_file():
        print(f"원장 없음(아직 실측 전): {runs_path}")
        return
    # last-wins: 같은 (포맷, 입력)은 최신 행만 채택 — 재실측(코드 스테일 무효분 등)이
    #   구행을 이중집계하지 않게. 원장은 append-only 유지, 집계에서만 dedup.
    latest: dict[tuple, dict] = {}
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("phase") != "FMT-QUAL":
            continue
        fmt = rec.get("params", {}).get("format")
        if fmt in FORMATS:
            latest[(fmt, rec.get("input", ""))] = rec  # 원장 순서=시간순 → 뒤가 최신
    rows: dict[str, list[dict]] = {f: [] for f in FORMATS}
    for rec in latest.values():
        rows[rec["params"]["format"]].append(rec)

    lines = ["# FMT-QUAL — 포맷 조판 품질 (자동: fmtqual_baseline.py summary)", "",
             "| 포맷 | n | 실패 | p50 gen_s | 컷 corr median | would-reject율 | 폴백율 |",
             "|---|---|---|---|---|---|---|"]
    for fmt in FORMATS:
        recs = [r for r in rows[fmt] if not r.get("error")]
        fails = sum(1 for r in rows[fmt] if r.get("error"))
        if not recs and not fails:
            continue
        met = [r.get("metrics", {}) for r in recs]
        times = [m["gen_s"] for m in met if m.get("gen_s") is not None]
        corrs = [m["cut_corr_median"] for m in met if m.get("cut_corr_median") is not None]
        total_cuts = sum(m.get("n_cuts_measured", 0) for m in met)
        rejects = sum(m.get("cuts_would_reject", 0) for m in met)
        fbacks = sum(m.get("cut_fallbacks", 0) for m in met)
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            fmt, len(recs), fails,
            round(statistics.median(times), 1) if times else "—",
            round(statistics.median(corrs), 3) if corrs else "—(배너=컷없음)",
            f"{rejects}/{total_cuts}" if total_cuts else "—",
            f"{fbacks}/{total_cuts}" if total_cuts else "—"))
    lines += ["", f"원장: {runs_path}",
              "판정: 컷 corr↓·would-reject율↓ = 다양성 개선. 조판 미감은 육안 정본(fmtqual/ 폴더)."]
    out = SUMMARY_DRY if args.dry_run else SUMMARY
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ 저장: {out}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="FMT-QUAL 포맷 조판 품질 베이스라인")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("--inputs-dir", required=True)
    pr.add_argument("--formats", default="detail,banner",
                    help="쉼표구분 (detail,cardnews,banner). 기본 detail,banner")
    pr.add_argument("--style", default="editorial", help="고정 스타일(포맷 비교 일관성)")
    pr.add_argument("--only", help="쉼표구분 파일명만")
    pr.add_argument("--sample", type=int, help="expected_mode별 앞 N개(3모드 균형)")
    pr.add_argument("--limit", type=int, help="앞 N개만(GPU 예산)")
    pr.add_argument("--dry-run", action="store_true")
    pr.set_defaults(fn=cmd_run)
    ps = sub.add_parser("summary")
    ps.add_argument("--dry-run", action="store_true")
    ps.set_defaults(fn=cmd_summary)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
