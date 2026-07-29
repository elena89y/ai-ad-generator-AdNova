"""v4 P6A — 오프라인 audit 배치 (워커 밖 CPU 전용) — 담당: 한의정.

runs.jsonl 최신 N건의 input/output을 읽어 후처리 채점하고 audit.jsonl에 적재한다.
평가 모델은 절대 워커 프로세스에 넣지 않는다(결정 D-7) — 본 스크립트는 별개 프로세스이며
시작 시 CPU를 강제한다(EasyOCR gpu=False 헬퍼, rembg CPU provider, metrics 디바이스 cpu).

항목(스펙 6A):
  - identity_dino / identity_lpips — 피사체 crop 정렬 후 비교(전체 프레임 비교 금지, #7):
    입력·출력 각각 rembg(CPU) 누끼 → alpha bbox 크롭 → 크롭끼리 비교. 합성·재연출처럼
    피사체 위치가 이동한 산출물에서도 배경 변화가 정체성 점수를 오염시키지 않는다.
  - product_delta_e — 피사체 크롭 간 LAB 평균 ΔE (scene_service의 numpy LAB 재사용).
  - ocr_preservation — 입력 피사체 크롭에서 읽힌 글자(라벨·로고)가 출력에도 남아있는 비율.
    입력에 글자가 없으면 None(채점 제외). EasyOCR은 text_clean.get_reader_cpu() 전용.
  - style_stats — 출력 전체 프레임 색 통계(style_finish 재사용). 스타일 발색 회귀 트립와이어.

사용 (VM, backend/ 에서 — 운영 워커 가동 중이어도 무방, CPU만 사용):
  ../.venv/bin/python scripts/v4_audit_runs.py audit --limit 30
  ../.venv/bin/python scripts/v4_audit_runs.py summary   # 축적분 캘리브레이션 통계(V4P6-001용)

의존성: requirements-eval.txt에만(easyocr·lpips·timm). 운영 requirements 추가 금지.
각 지표는 실패 시 None 기록(크래시 금지) — metrics.py와 동일 규약.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

# CPU 강제 — import 순서상 어떤 지표 모델보다 먼저 설정돼야 한다.
os.environ.setdefault("ADNOVA_EVAL_DEVICE", "cpu")
os.environ["COMPOSE_REMBG_CUDA"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger(__name__)

RUNS_PATH = Path(__file__).resolve().parents[1] / "experiments" / "runs.jsonl"
AUDIT_PATH = Path(__file__).resolve().parents[1] / "experiments" / "audit.jsonl"

# OCR 보존율 매칭 전 정규화 — 대소문자·공백·구두점 차이는 보존으로 인정
_NORM_PAT = re.compile(r"[^0-9a-zA-Z가-힣]+")


def _select_runs(runs_path: Path, limit: int, phase_prefix: str = "") -> list[dict]:
    """runs.jsonl 최신 limit건 중 input/output 파일이 실존하는 행만 고른다."""
    if not runs_path.is_file():
        return []
    rows: list[dict] = []
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue  # 손상 행은 건너뛴다 — audit이 원장 오염으로 죽으면 안 됨
        rows.append(row)
    picked = []
    for row in reversed(rows):  # 최신부터
        if phase_prefix and not str(row.get("phase", "")).startswith(phase_prefix):
            continue
        inp, out = row.get("input"), row.get("output")
        if not inp or not out:
            continue
        if not (Path(inp).is_file() and Path(out).is_file()):
            continue
        picked.append(row)
        if len(picked) >= limit:
            break
    return picked


def _normalize_text(text: str) -> str:
    return _NORM_PAT.sub("", text).lower()


def ocr_preservation(texts_in: list[str], texts_out: list[str]) -> Optional[float]:
    """입력에서 읽힌 글자가 출력에서도 발견되는 비율. 입력에 글자 없으면 None(채점 제외)."""
    normalized_in = [t for t in (_normalize_text(t) for t in texts_in) if len(t) >= 2]
    if not normalized_in:
        return None
    joined_out = " ".join(_normalize_text(t) for t in texts_out)
    kept = sum(1 for t in normalized_in if t in joined_out)
    return round(kept / len(normalized_in), 4)


def _ocr_texts(image_path: str) -> list[str]:
    """CPU EasyOCR로 이미지의 텍스트만 추출(신뢰도 문턱은 text_clean과 동일)."""
    from app.harness import text_clean

    reader = text_clean.get_reader_cpu()
    results = reader.readtext(image_path)
    return [text for _bbox, text, prob in results if prob >= text_clean.CONF_THRESHOLD]


def _subject_crop(image_path: str) -> "object":  # noqa: ANN401 — PIL lazy import
    """rembg(CPU) 누끼 → alpha bbox 크롭. 실패 시 원본 반환(크롭 정렬 포기, 전체 비교)."""
    from PIL import Image

    from app.services import scene_service

    img = Image.open(image_path).convert("RGB")
    try:
        cut = scene_service.cutout(image_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("subject crop 실패(%s): %s", image_path, exc)
        return img
    if not cut.get("ok"):
        return img
    bbox = cut["rgba"].split()[-1].getbbox()
    return img.crop(bbox) if bbox else img


def product_delta_e(crop_in, crop_out, size: int = 256) -> Optional[float]:  # noqa: ANN001
    """피사체 크롭 간 LAB 평균 ΔE. scene_service의 numpy LAB 재사용(신규 의존성 0)."""
    try:
        import numpy as np
        from PIL import Image

        from app.services import scene_service

        a = np.asarray(crop_in.resize((size, size), Image.LANCZOS).convert("RGB"))
        b = np.asarray(crop_out.resize((size, size), Image.LANCZOS).convert("RGB"))
        lab_a = scene_service._rgb_to_lab(a)
        lab_b = scene_service._rgb_to_lab(b)
        return round(float(np.sqrt(((lab_a - lab_b) ** 2).sum(axis=-1)).mean()), 3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("product_delta_e 실패: %s", exc)
        return None


def audit_run(row: dict, work_dir: Path) -> dict:
    """run 1건 채점. 각 지표는 독립 실패(None) — 하나 죽어도 나머지는 기록한다."""
    inp, out = str(row["input"]), str(row["output"])
    result: dict = {
        "run_id": row.get("run_id") or row.get("id"),
        "ts": row.get("ts"),
        "phase": row.get("phase"),
        "engine": row.get("engine"),
        "input": inp,
        "output": out,
        "audited_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    crop_in = crop_out = None
    try:
        crop_in = _subject_crop(inp)
        crop_out = _subject_crop(out)
    except Exception as exc:  # noqa: BLE001
        logger.warning("crop 단계 실패: %s", exc)

    # DINO/LPIPS — 크롭을 임시 파일로 저장해 crop 정렬 비교(#7: 전체 프레임 비교 금지)
    result["identity_dino"] = result["identity_lpips"] = None
    if crop_in is not None and crop_out is not None:
        try:
            from app.harness import metrics

            p_in = work_dir / "crop_in.png"
            p_out = work_dir / "crop_out.png"
            crop_in.save(p_in)
            crop_out.save(p_out)
            result["identity_dino"] = metrics.identity_dino(str(p_in), str(p_out))
            result["identity_lpips"] = metrics.identity_lpips(str(p_in), str(p_out))
        except Exception as exc:  # noqa: BLE001
            logger.warning("identity 지표 실패: %s", exc)

        result["product_delta_e"] = product_delta_e(crop_in, crop_out)
    else:
        result["product_delta_e"] = None

    # OCR 보존율 — 입력 피사체 크롭의 글자(라벨·로고)가 출력에 남아있는가
    try:
        p_in = work_dir / "crop_in.png"
        texts_in = _ocr_texts(str(p_in)) if p_in.is_file() else _ocr_texts(inp)
        texts_out = _ocr_texts(out)
        result["ocr_preservation"] = ocr_preservation(texts_in, texts_out)
        result["ocr_texts_in"] = texts_in[:5]
    except Exception as exc:  # noqa: BLE001
        logger.warning("OCR 지표 실패: %s", exc)
        result["ocr_preservation"] = None
        result["ocr_texts_in"] = []

    # style_stats — 출력 프레임 색 통계(발색 회귀 트립와이어)
    try:
        from app.services import style_finish

        result["style_stats"] = {
            k: round(v, 4) for k, v in style_finish.style_stats(out).items()
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("style_stats 실패: %s", exc)
        result["style_stats"] = None

    return result


def cmd_audit(args) -> None:
    runs = _select_runs(Path(args.runs), args.limit, args.phase_prefix)
    if not runs:
        sys.exit("채점할 run 없음 (input/output 실존 행 기준)")
    already = set()
    audit_path = Path(args.out)
    if audit_path.is_file() and not args.re_audit:
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            try:
                already.add(json.loads(line).get("run_id"))
            except Exception:  # noqa: BLE001
                continue
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    done = skipped = 0
    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        with open(audit_path, "a", encoding="utf-8") as fp:
            for i, row in enumerate(runs, 1):
                rid = row.get("run_id") or row.get("id")
                if rid in already:
                    skipped += 1
                    continue
                started = time.perf_counter()
                entry = audit_run(row, work_dir)
                entry["audit_seconds"] = round(time.perf_counter() - started, 2)
                fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
                fp.flush()
                done += 1
                print(f"[{i}/{len(runs)}] {rid} engine={entry.get('engine')} "
                      f"dino={entry['identity_dino']} lpips={entry['identity_lpips']} "
                      f"dE={entry['product_delta_e']} ocr={entry['ocr_preservation']} "
                      f"({entry['audit_seconds']}s)")
    print(f"완료: 채점 {done} · 기채점 스킵 {skipped} → {audit_path}")


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[idx]


def cmd_summary(args) -> None:
    """축적된 audit.jsonl의 지표 분포 — V4P6-001 임계값 캘리브레이션용 표."""
    audit_path = Path(args.out)
    if not audit_path.is_file():
        sys.exit(f"audit 없음: {audit_path}")
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    by_prefix: dict[str, list[dict]] = {}
    for e in entries:
        prefix = str(e.get("engine") or "unknown").split(":")[0]
        by_prefix.setdefault(prefix, []).append(e)
    metrics_keys = ("identity_dino", "identity_lpips", "product_delta_e", "ocr_preservation")
    print(f"총 {len(entries)}건 (경로 {len(by_prefix)}종)"
          + (" — ⚠️ 30건 미만, 임계값 확정 보류" if len(entries) < 30 else ""))
    for prefix, group in sorted(by_prefix.items()):
        print(f"\n== engine={prefix} ({len(group)}건) ==")
        for key in metrics_keys:
            vals = sorted(v for v in (e.get(key) for e in group) if isinstance(v, (int, float)))
            if not vals:
                print(f"  {key:18s}: (값 없음)")
                continue
            print(f"  {key:18s}: n={len(vals)} min={vals[0]:.3f} "
                  f"p25={_percentile(vals, 0.25):.3f} p50={_percentile(vals, 0.50):.3f} "
                  f"p75={_percentile(vals, 0.75):.3f} max={vals[-1]:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit")
    a.add_argument("--runs", default=str(RUNS_PATH))
    a.add_argument("--out", default=str(AUDIT_PATH))
    a.add_argument("--limit", type=int, default=30)
    a.add_argument("--phase-prefix", default="", help='예: "V4" — v4 경로만 채점')
    a.add_argument("--re-audit", action="store_true", help="기채점 run도 다시 채점")
    a.set_defaults(fn=cmd_audit)
    s = sub.add_parser("summary")
    s.add_argument("--out", default=str(AUDIT_PATH))
    s.set_defaults(fn=cmd_summary)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
