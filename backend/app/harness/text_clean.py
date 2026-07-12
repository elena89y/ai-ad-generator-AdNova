"""레퍼런스 이미지 텍스트 클렌징 — 담당: 한의정 (Phase 5 플라이휠 데이터 준비).

스타일 씬 레퍼런스(에디토리얼·팝 등)에는 광고 카피·브랜드 텍스트가 박혀 있다.
그대로 학습(LoRA)에 쓰면 모델이 폰트를 '가짜 글자 노이즈'로 배워 생성 품질이 붕괴하고
(트랩 #3), 오토캡션 VLM 도 텍스트에 끌려 오판한다(AUTOCAP-001 의 UI 붕괴와 동일 기전).

파이프라인: EasyOCR(ko+en)로 텍스트 bbox 탐지 → OpenCV TELEA 인페인트로 제거 →
텍스트가 있던 자리를 [text_space] 메타데이터로 반환(여백 인지 학습용 — 텍스트 자리
= 디자이너가 잡은 카피 공간이므로 그대로 여백 토큰이 된다).

사용: clean_image(src, dst) → dict(메타). 배치는 clean_batch().
⚠️ GPU VM 전용(EasyOCR 은 VM venv 에만 설치). reader 는 lazy 싱글턴(로드 ~수초).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_reader = None

# 오탐(제품 로고·질감을 글자로 착각) 방지: 신뢰도 문턱. 낮추면 과삭제 위험.
CONF_THRESHOLD = 0.30
# 텍스트가 프레임의 이 비율을 넘으면 '텍스트 포스터'로 보고 학습셋에서 제외 권고.
TEXT_HEAVY_PCT = 0.25


def _get_reader():
    """EasyOCR reader lazy 싱글턴 (ko+en, GPU)."""
    global _reader
    if _reader is None:
        import easyocr

        logger.info("EasyOCR 로드 (ko+en)")
        _reader = easyocr.Reader(["ko", "en"], gpu=True, verbose=False)
    return _reader


def _region_token(cx: float, cy: float) -> str:
    """bbox 중심(상대좌표) → 9분면 위치 토큰 (여백 인지 메타데이터)."""
    col = "left" if cx < 1 / 3 else ("right" if cx > 2 / 3 else "center")
    row = "top" if cy < 1 / 3 else ("bottom" if cy > 2 / 3 else "middle")
    return f"{row}_{col}" if not (row == "middle" and col == "center") else "center"


def clean_image(src: str, dst: str, conf: float = CONF_THRESHOLD) -> dict:
    """이미지 한 장 텍스트 제거 → dst 저장. 메타데이터 dict 반환.

    반환: {"text_regions": [위치토큰...], "text_area_pct": float,
           "n_boxes": int, "text_heavy": bool, "sample_texts": [읽힌 글자 상위 3]}
    text_heavy=True 면 학습셋 제외 권고(텍스트가 화면 1/4 이상 = 타이포 포스터).
    """
    import cv2
    import numpy as np

    img = cv2.imread(str(src))
    if img is None:
        raise ValueError(f"이미지 로드 실패: {src}")
    H, W = img.shape[:2]

    results = _get_reader().readtext(img)
    mask = np.zeros((H, W), dtype=np.uint8)
    regions: list[str] = []
    texts: list[str] = []
    area = 0
    for bbox, text, prob in results:
        if prob < conf:
            continue
        pts = np.array(bbox, dtype=np.int32)
        x0, y0 = pts.min(axis=0)
        x1, y1 = pts.max(axis=0)
        # 인페인트 경계 잔상 방지: bbox 를 살짝 팽창
        pad = max(2, int(min(H, W) * 0.004))
        x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
        x1, y1 = min(W, x1 + pad), min(H, y1 + pad)
        mask[y0:y1, x0:x1] = 255
        area += (x1 - x0) * (y1 - y0)
        regions.append(_region_token((x0 + x1) / 2 / W, (y0 + y1) / 2 / H))
        texts.append(text)

    if mask.any():
        cleaned = cv2.inpaint(img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    else:
        cleaned = img
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), cleaned)

    pct = float(area) / float(H * W)  # area 가 numpy int 라 명시 캐스팅(JSON 직렬화)
    # 위치 토큰 중복 제거(순서 유지)
    uniq = list(dict.fromkeys(regions))
    # UI 잔재 감지: 크롭이 덜 된 스크린샷(인스타 게시물/좋아요/시각 등) → 재크롭 대상 플래그
    import re

    ui_pat = re.compile(r"게시물|좋아요|팔로우|댓글|공유|저장|^\d{1,2}:\d{2}$|Instagram", re.IGNORECASE)
    ui_residual = any(ui_pat.search(t.strip()) for t in texts)
    return {"text_regions": uniq, "text_area_pct": round(pct, 4), "n_boxes": len(texts),
            "text_heavy": bool(pct > TEXT_HEAVY_PCT), "ui_residual": bool(ui_residual),
            "sample_texts": texts[:3]}


def clean_batch(src_dir: str, dst_dir: str, meta_path: Optional[str] = None) -> list[dict]:
    """폴더 일괄 클렌징. 메타를 jsonl 로 저장(옵션). [{image, ...메타}] 반환."""
    rows = []
    src_p = Path(src_dir)
    files = [f for f in sorted(src_p.glob("*.png")) + sorted(src_p.glob("*.jpg"))
             if not f.name.startswith("._")]  # macOS AppleDouble 메타파일 제외
    for f in files:
        try:
            meta = clean_image(str(f), str(Path(dst_dir) / f.name))
        except Exception as e:  # noqa: BLE001 — 배치는 한 장 실패로 안 멈춤
            logger.warning("클렌징 실패 %s: %s", f.name, e)
            meta = {"error": str(e)}
        rows.append({"image": f.name, **meta})
    if meta_path:
        with open(meta_path, "w", encoding="utf-8") as fp:
            for r in rows:
                fp.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows
