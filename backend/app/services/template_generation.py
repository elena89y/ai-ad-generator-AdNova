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

관측성: 정상 경로(run_from_upload_v2)와 동일하게 RunLogger 로 감싼다 → KPI 원장
(runs.jsonl)에 시간·openai·image_api(gpt-image-2 edit 장당) 비용이 적재되고, Langfuse
트레이스 1건으로 묶인다. 문구는 정상 경로와 같은 _generate_copy 라우터를 태워
copy_graph(LangGraph) 품질 게이트를 공유한다. edit 은 GPU 미점유이므로 gpu_used=False
를 명시해 KPI 가 GPU 비용을 오계상하지 않도록 한다(하이브리드 A/B 공정성).
"""
from __future__ import annotations

import logging
import re
import secrets
import shutil
import time
from pathlib import Path

from . import api_image_service, gpt_service, image_service, template_crop, template_service
from .generation_service import GenerationOutput, _generate_copy, _stage
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

# 샌드위치 최종 규칙 (2026-07-23 비누 사고 대응): 프리앰블(앞)의 추상 지시가 씬의 구체
# 예시 명사에 지는 것이 실측됨(strict도 뚫림) → 프롬프트 '뒤'에도 최종 우선 규칙을 반복해
# recency 우위를 확보한다. loose 포함 전 등급 적용 — 텍스처 매크로형(04·30)도 "표면·재질"
# 문구로 커버되므로 예외 없음.
_FINAL_RULE = (
    "\n\n[최종 우선 규칙] 이 이미지의 주인공은 업로드한 사진 속 피사체(또는 그 표면·재질)다. "
    "위 지시문에 예시 제품·음식이 확정문으로 등장하더라도 그것을 새로 생성하지 말고 그 자리에 "
    "업로드한 피사체를 놓는다. 업로드한 피사체가 아닌 다른 제품·음식이 화면에 존재하면 실패다."
)

# 카탈로그 프롬프트 내 대괄호 플레이스홀더 ([MENU NAME] 등, 모노브 수집 영어 장문형에 존재)
_PLACEHOLDER_RE = re.compile(r"\[[A-Z][A-Z \-]+\]")


def build_instruction(catalog_id: str, product_name: str = "",
                      extra_request: str = "") -> tuple[str, str, str]:
    """template_id → (지시문, identity_grade, size). 지시문 = 프리앰블 + (제품명) + 원장 프롬프트 + 최종규칙 (+추가요청)."""
    t = template_service.get_catalog_template(catalog_id)
    name = product_name.strip()
    name_line = f"제품/메뉴명: {name}\n\n" if name else ""
    prompt = t.prompt
    # [MENU NAME] 류 플레이스홀더 치환 — 제품명이 있으면 그대로 박고("exactly as written" 지시와 정합),
    # 없으면 리터럴 토큰이 이미지에 구워지지 않게 자체 결정 지시로 폴백 (tpl_50은 프롬프트에 폴백 조항이 없음).
    if name:
        prompt = prompt.replace("[MENU NAME]", name)
    placeholder_note = ""
    if _PLACEHOLDER_RE.search(prompt):
        placeholder_note = (
            "\n\n[플레이스홀더 처리] 지시문의 [MENU NAME]·[MENU DESCRIPTION] 같은 대괄호 토큰은 "
            "실제 문구가 아니다 — 업로드 피사체를 분석해 어울리는 짧은 문구로 스스로 정해 넣고, "
            "대괄호 토큰 자체를 이미지에 그리지 않는다."
        )
    instruction = _PREAMBLE.get(t.identity_grade, "") + name_line + prompt + _FINAL_RULE + placeholder_note
    if extra_request and extra_request.strip():
        # 사용자 추가 요청은 연출·분위기·구도 참고용. 제품/음식의 정체성·라벨·형태는 위 지침이 우선.
        instruction += (
            f"\n\n[사용자 추가 요청 — 연출·분위기·구도 참고] {extra_request.strip()}\n"
            "단, 업로드한 제품/음식의 형태·색·라벨·정체성은 위 지침을 우선하며 이 요청으로 왜곡하지 않는다."
        )
    return instruction, t.identity_grade, t.size


def generate_from_template(
    image_path: str,
    catalog_id: str,
    product: ProductInfo,
    use_vision: bool = False,
    quality: str = "low",
    extra_request: str = "",
    run=None,  # noqa: ANN001 — 상위가 이미 RunLogger 를 열었으면 전달, 아니면 자체 개설
) -> GenerationOutput:
    """업로드 이미지 + 템플릿 연출로 광고 1장 생성 → GenerationOutput.

    strict 등급은 프리앰블이 라벨·형태 보존을 강제한다. 이미지 엔진 gpt-image-2 edit.
    extra_request = 사용자 추가 요청(연출·분위기 참고, 정체성은 프리앰블 우선).
    run 이 없으면 자체 RunLogger 를 열어 KPI 원장·Langfuse·usage 를 정상 경로와 동일하게 적재.
    """
    if run is not None:  # 상위 원장에 합류
        return _generate_impl(image_path, catalog_id, product, use_vision, quality, extra_request, run)

    try:
        from ..harness.run_logger import RunLogger

        rl = RunLogger(
            phase="TPL", mode="pending", engine=f"template:{catalog_id}",
            input=image_path, seed=0,
            params={"catalog_id": catalog_id, "name": product.name, "quality": quality,
                    "request": "generate", "template": True,
                    "extra_request": extra_request or None},
        )
    except Exception as exc:  # noqa: BLE001 — 트레이싱 장애가 생성을 막으면 안 됨
        logger.warning("RunLogger 초기화 실패 — 원장 없이 진행: %s", exc)
        return _generate_impl(image_path, catalog_id, product, use_vision, quality, extra_request, None)

    with rl:
        out = _generate_impl(image_path, catalog_id, product, use_vision, quality, extra_request, rl)
        # API edit = GPU 미점유. 명시해야 KPI 가 GPU 비용을 오계상하지 않음(하이브리드 공정성).
        rl.set_meta(mode=out.domain, engine=f"template:{catalog_id}", gpu_used=False, seed=0)
        rl.set_output(out.final_image_path)
    return out


def _generate_impl(
    image_path: str,
    catalog_id: str,
    product: ProductInfo,
    use_vision: bool,
    quality: str,
    extra_request: str,
    run,  # noqa: ANN001 — RunLogger | None
) -> GenerationOutput:
    """실제 생성 본체 — RunLogger 컨텍스트(있으면) 안에서 edit·문구를 단계별로 계측한다."""
    t = template_service.get_catalog_template(catalog_id)
    instruction, grade, size = build_instruction(catalog_id, product.name, extra_request)
    style_badge = _FINISH_STYLE.get(t.finish, StylePreset.EDITORIAL)
    # 템플릿별 품질(catalog quality) 우선 — 질감 중요한 음식 템플릿만 medium, 나머지 low.
    q = t.quality or quality
    asset_id = secrets.token_hex(6)  # 12자리 hex (^[a-f0-9]{12}$)
    logger.info("template 생성: id=%s grade=%s q=%s asset=%s", catalog_id, grade, q, asset_id)

    t0 = time.time()
    with _stage(run, "generate"):
        raw = api_image_service.edit_image(
            image_path, instruction, out_dir=str(image_service.RESULTS_DIR),
            size=size, quality=q, run=run,  # run 전달 → image_api 비용 원장 적재
        )
    # asset_id 규약 파일명으로 정착 (서빙·재생성 계약과 통일)
    final = image_service.RESULTS_DIR / f"{asset_id}_template.png"
    shutil.move(raw, final)
    # 템플릿별 결정론적 후처리 크롭 (예: 단면 히어로 = 층 꽉 참 + 한쪽 끝 노출).
    # 프롬프트로 풀 슬라이스를 여백과 함께 생성 → 여기서 구도를 확정한다(복불복 제거).
    if t.post_crop:
        with _stage(run, "post_crop"):
            template_crop.apply(t.post_crop, str(final))
    gen_s = round(time.time() - t0, 2)

    # 문구 — 정상 경로와 동일한 _generate_copy 라우터(copy_graph 품질 게이트 공유). 실패해도 폴백.
    try:
        with _stage(run, "copy"):
            copy = _generate_copy(str(final), product, style_badge, use_vision)
        copy_text = copy.copy_text.strip()
    except Exception:  # noqa: BLE001
        logger.exception("template 문구 생성 실패 — 제품명 폴백")
        copy_text = product.name
    try:
        with _stage(run, "platform_copy"):
            platform_copies = gpt_service.generate_platform_copy(product, style_badge)
    except Exception:  # noqa: BLE001
        platform_copies = {}

    return GenerationOutput(
        final_image_path=str(final),
        asset_id=asset_id,
        seed=0,
        style=style_badge,
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
