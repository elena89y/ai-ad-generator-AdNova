"""template_id 기반 광고 생성 (TEMPLATE-PIPE-V2, 2026-07-21) — 담당: 한의정.

기존 스타일-프리셋 생성과 별개 경로. 카탈로그 원장(catalog_v1.json)의 고유 연출
프롬프트를 서버측에서 조회해 그 연출로 생성한다. 프롬프트는 클라이언트/API 응답에
노출하지 않는다(서버측 전용).

정체성 계약(라벨·형태 보존)은 identity_grade 로 프리앰블 강도를 차등한다:
  strict   = 사물/뷰티 제품컷 — 라벨 브랜드명·문자·로고까지 100% 보존, 제품 재생성 금지
  standard = 음식/그래픽 — 구성 재료·형태 보존, 없던 재료·문자 생성 금지
  loose    = 재질 각인 등 — 최소 제약

생성 엔진: gpt-image-2 edit(API). 라이브 로컬 경로(Kontext)는 마스크·negative 없이
라벨을 재렌더해 위조하므로(CLAUDE.md 함정 #3) template 경로에서는 배제한다. edit 은
TPL-001·검증 실측에서 라벨 보존 우수(TWININGS·PHILIPS 유지)로 확인됨.

반환은 GenerationOutput — 기존 _to_response / _record_generated_result 인프라를 재사용해
DB 저장·이미지 서빙·재생성 계약을 그대로 태운다.
"""
from __future__ import annotations

import logging
import secrets
import shutil
import time
from pathlib import Path

from . import api_image_service, gpt_service, image_service, template_service
from .generation_service import GenerationOutput
from .prompt_service import ProductInfo
from ..schemas.ads import StylePreset

logger = logging.getLogger(__name__)

# identity_grade → 정체성 보존 프리앰블 (연출 프롬프트 앞에 주입)
_PREAMBLE = {
    "strict": (
        "업로드한 사진 속 제품이 이 이미지의 유일한 주인공이다. 제품의 형태·비율·색·재질, "
        "그리고 라벨의 브랜드명·문자·로고를 원본 그대로 100% 보존한다 — 글자 하나도 바꾸거나 "
        "새로 만들지 않는다. 아래 연출 지시는 배경·조명·구도 참고일 뿐, 제품 자체(용기·라벨)는 "
        "절대 재생성하지 않는다. 지시문에 예시로 등장하는 다른 제품 이름은 무시하고 업로드 "
        "제품으로 대체한다.\n\n"
    ),
    "standard": (
        "업로드한 사진 속 음식·제품이 주인공이다. 구성 재료·형태·색을 원본 그대로 보존하고, "
        "원본에 없는 재료·문자를 만들지 않는다. 아래 연출의 예시 피사체는 구도 참고일 뿐, "
        "반드시 업로드 피사체로 대체해 연출한다.\n\n"
    ),
    "loose": "",
}

# 카탈로그 finish → 히스토리 뱃지용 대표 StylePreset (연출 자체는 프롬프트가 결정, 뱃지 표시용)
_FINISH_STYLE = {"photographic": StylePreset.EDITORIAL, "graphic": StylePreset.POP,
                 "stylized": StylePreset.WARM_VINTAGE}
# identity_grade → GenerationOutput.domain (DETAIL-001 소비)
_GRADE_DOMAIN = {"strict": "object", "standard": "food", "loose": "object"}


def build_instruction(catalog_id: str, product_name: str = "") -> tuple[str, str, str]:
    """template_id → (지시문, identity_grade, size). 지시문 = 프리앰블 + (제품명) + 원장 프롬프트."""
    t = template_service.get_catalog_template(catalog_id)
    name_line = f"제품/메뉴명: {product_name}\n\n" if product_name.strip() else ""
    instruction = _PREAMBLE.get(t.identity_grade, "") + name_line + t.prompt
    return instruction, t.identity_grade, t.size


def generate_from_template(
    image_path: str,
    catalog_id: str,
    product: ProductInfo,
    use_vision: bool = False,
    quality: str = "low",
    run=None,  # noqa: ANN001 — RunLogger optional (KPI 원장 합류)
) -> GenerationOutput:
    """업로드 이미지 + 템플릿 연출로 광고 1장 생성 → GenerationOutput.

    strict 등급은 프리앰블이 라벨·형태 보존을 강제한다. 이미지 엔진 gpt-image-2 edit.
    """
    t = template_service.get_catalog_template(catalog_id)
    instruction, grade, size = build_instruction(catalog_id, product.name)
    asset_id = secrets.token_hex(6)  # 12자리 hex (^[a-f0-9]{12}$)
    logger.info("template 생성: id=%s grade=%s asset=%s", catalog_id, grade, asset_id)

    t0 = time.time()
    raw = api_image_service.edit_image(
        image_path, instruction, out_dir=str(image_service.RESULTS_DIR),
        size=size, quality=quality, run=run,
    )
    # asset_id 규약 파일명으로 정착 (서빙·재생성 계약과 통일)
    final = image_service.RESULTS_DIR / f"{asset_id}_template.png"
    shutil.move(raw, final)
    gen_s = round(time.time() - t0, 2)

    # 문구 — 생성 이미지 기반 (FR-09). 실패해도 이미지는 유효하므로 폴백.
    try:
        copy = gpt_service.generate_copy(str(final), product, _FINISH_STYLE.get(t.finish, StylePreset.EDITORIAL), use_vision=use_vision)
        copy_text = copy.copy_text.strip()
    except Exception:  # noqa: BLE001
        logger.exception("template 문구 생성 실패 — 제품명 폴백")
        copy_text = product.name
    try:
        platform_copies = gpt_service.generate_platform_copy(product, _FINISH_STYLE.get(t.finish, StylePreset.EDITORIAL))
    except Exception:  # noqa: BLE001
        platform_copies = {}

    return GenerationOutput(
        final_image_path=str(final),
        asset_id=asset_id,
        seed=0,
        style=_FINISH_STYLE.get(t.finish, StylePreset.EDITORIAL),
        copy_text=copy_text,
        platform_copies=platform_copies,
        poster=True,  # 템플릿 연출에 타이포가 포함됨
        generate_seconds=gen_s,
        harmonize_seconds=0.0,
        image_without_typography_path=str(final),  # 단일본 (타이포 구움) — 페어 폴백 안전값
        image_with_typography_path=str(final),
        typography_layout="template",
        domain=_GRADE_DOMAIN.get(grade, "food"),
    )
