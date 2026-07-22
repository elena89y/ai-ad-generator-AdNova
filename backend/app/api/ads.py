"""광고 스타일/생성 API 라우터.

담당: 한의정
엔드포인트:
  POST /ads/style      — 스타일 결정 2경로 (FR-05)
  POST /ads/generate   — 통합 파이프라인: 전처리→생성→조화→문구(→포스터) (FR-06~09)
  POST /ads/regenerate — 동일 입력 · 새 seed 재생성 (FR-12)
  GET  /ads/image/{filename} — 생성 결과 이미지 서빙 (프론트 표시·다운로드용)
  GET  /ads/templates        — 템플릿 프리셋 목록 (v6 T4; 항목의 style_preset/knob 을
                               기존 /ads/generate 에 그대로 실어 보낸다 — 신규 생성 계약 없음)
  GET  /ads/template-thumb/{template_id} — 템플릿 정적 썸네일 (assets, 코드 드로잉)

프론트(frontend/app.py) 연동 스펙에 맞춘 구성. DB 이력 저장(FR-19)은
advertisements CRUD(김범수님) 연동 시 추가 예정.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.observability import propagate_attributes
from ..core.security import get_current_user
from ..crud.advertisement import create_advertisement
from ..crud.billing import get_subscription_by_user
from ..crud.credits import (
    consume_bonus_credit,
    consume_free_credit,
    consume_premium_credit,
    restore_bonus_credit,
    restore_free_credit,
    restore_premium_credit,
)
from ..crud.history import create_history
from ..crud.image import create_image, get_image_by_id
from ..database.connection import get_db
from ..database.models import History, Image, User
from ..schemas.ads import (
    AdPurpose,
    GenerateAdResponse,
    ProductInfo,
    RegenerateAdRequest,
    StylePreset,
    StyleRequest,
    StyleResponse,
)
from ..services import (
    generation_client,
    generation_service,
    gpt_service,
    image_service,
    style_service,
    template_generation,
    template_service,
)
from ..services.prompt_service import build_image_prompt
from ..services.upload_validation import read_image_upload_file_sync

router = APIRouter(prefix="/ads", tags=["ads"])

TEMP_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "temp_uploads"


def _remove_temporary_upload(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.parent.resolve() == TEMP_UPLOAD_DIR.resolve():
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _consume_generation_credit(db: Session, user_id: int) -> str:
    if consume_bonus_credit(db, user_id) is not None:
        return "bonus"

    subscription = get_subscription_by_user(db, user_id)
    is_premium = bool(
        subscription
        and subscription.plan == "premium"
        and subscription.status == "active"
    )
    if is_premium:
        if consume_premium_credit(
            db,
            user_id,
            next_reset_at=subscription.current_period_end,
        ) is None:
            raise HTTPException(
                status_code=403,
                detail="이번 달 프리미엄 크레딧을 모두 사용했습니다.",
            )
        return "premium"

    if consume_free_credit(db, user_id) is None:
        raise HTTPException(
            status_code=403,
            detail="무료 체험 횟수를 모두 사용했습니다. 프리미엄 플랜을 이용해 주세요.",
        )
    return "free"


def _restore_generation_credit(db: Session, user_id: int, credit_type: str) -> None:
    if credit_type == "bonus":
        restore_bonus_credit(db, user_id)
        return
    if credit_type == "premium":
        subscription = get_subscription_by_user(db, user_id)
        restore_premium_credit(
            db,
            user_id,
            next_reset_at=(
                subscription.current_period_end if subscription is not None else None
            ),
        )
        return
    restore_free_credit(db, user_id)


def _to_response(out: generation_service.GenerationOutput) -> GenerateAdResponse:
    """순수 생성 결과 → API 응답. image_url 은 프리픽스 포함 서빙 경로로 통일."""
    def image_url(path: str | None) -> str | None:
        return f"{settings.API_PREFIX}/ads/image/{Path(path).name}" if path else None

    return GenerateAdResponse(
        asset_id=out.asset_id,
        seed=out.seed,
        style=out.style,
        copy_text=out.copy_text,
        platform_copies=out.platform_copies,
        image_url=f"{settings.API_PREFIX}/ads/image/{Path(out.final_image_path).name}",
        poster=out.poster,
        image_without_typography_url=image_url(out.image_without_typography_path),
        image_with_typography_url=image_url(out.image_with_typography_path),
        typography_enabled=out.poster,
        typography_layout=out.typography_layout,
        generate_seconds=out.generate_seconds,
        harmonize_seconds=out.harmonize_seconds,
    )


def _compose_banner_response(
    result: GenerateAdResponse,
    product_name: str,
    sizes: list[str] | None = None,
) -> GenerateAdResponse:
    """기존 히어로를 재생성하지 않고 v5 배너 팩으로 확장한다."""
    from ..services import pipeline_v5
    from ..services.pipeline_v5.hero import hero_from_existing

    source_url = result.image_without_typography_url or result.image_url
    source = image_service.RESULTS_DIR / Path(source_url).name
    if not source.is_file():
        raise ValueError(f"배너 원본 이미지를 찾을 수 없습니다: {source.name}")
    headline, _, subcopy = result.copy_text.partition("\n")
    hero = hero_from_existing(
        str(source), product_name=product_name,
        headline=headline.strip() or product_name, subcopy=subcopy.strip(),
    )
    output_dir = image_service.RESULTS_DIR / f"{result.asset_id}_banner"
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = pipeline_v5.generate_v5(
        str(source), product_name, purpose=AdPurpose.BANNER,
        hero_asset=hero, sizes=sizes, output_dir=str(output_dir),
    )
    urls = []
    for path in rendered.outputs:
        source_path = Path(path)
        served = image_service.RESULTS_DIR / f"{result.asset_id}_{source_path.name}"
        served.write_bytes(source_path.read_bytes())
        urls.append(f"{settings.API_PREFIX}/ads/image/{served.name}")
    return result.model_copy(update={"purpose": AdPurpose.BANNER, "format_outputs": urls})


def _record_generated_result(
    db: Session,
    *,
    user_id: int,
    input_image_id: Optional[int],
    product_name: Optional[str],
    style: StylePreset,
    poster: bool,
    prompt_for_db: str,
    result: GenerateAdResponse,
    action_type: str,
    request_data: str,
) -> int:
    output_filename = Path(result.image_url).name
    output_path = image_service.RESULTS_DIR / output_filename
    try:
        output_image = create_image(
            db,
            user_id=user_id,
            image_type="generated",
            original_filename=output_filename,
            stored_filename=output_filename,
            file_path=str(output_path),
            image_url=result.image_url,
            content_type="image/png",
            file_size=output_path.stat().st_size if output_path.exists() else None,
            commit=False,
        )

        # 타이포 ON/OFF 두 변형 모두 GET /ads/image/{filename}로 조회 가능해야 하는데,
        # get_result_image()가 Image.stored_filename 정확일치로 소유자를 확인한다.
        # 위에서 result.image_url(선택된 한쪽)만 등록하면 반대쪽 변형은 파일은 존재해도
        # DB row가 없어 404("이미지 없음")가 난다(2026-07-20, TOGGLE-001). 나머지 변형도 등록.
        for variant_url in (result.image_without_typography_url, result.image_with_typography_url):
            if not variant_url:
                continue
            variant_filename = Path(variant_url).name
            if variant_filename == output_filename:
                continue
            variant_path = image_service.RESULTS_DIR / variant_filename
            create_image(
                db,
                user_id=user_id,
                image_type="generated",
                original_filename=variant_filename,
                stored_filename=variant_filename,
                file_path=str(variant_path),
                image_url=variant_url,
                content_type="image/png",
                file_size=variant_path.stat().st_size if variant_path.exists() else None,
                commit=False,
            )

        # 카드뉴스/상세페이지/배너 결과 파일(format_outputs)도 같은 이유로 등록해야 조회된다
        # (2026-07-20, TOGGLE-002) — 등록 안 하면 파일은 있어도 프론트에서 빈 썸네일로만 보임.
        for format_url in result.format_outputs or []:
            format_filename = Path(format_url).name
            if format_filename == output_filename:
                continue
            format_path = image_service.RESULTS_DIR / format_filename
            create_image(
                db,
                user_id=user_id,
                image_type="generated",
                original_filename=format_filename,
                stored_filename=format_filename,
                file_path=str(format_path),
                image_url=format_url,
                content_type="image/jpeg",
                file_size=format_path.stat().st_size if format_path.exists() else None,
                commit=False,
            )

        advertisement = create_advertisement(
            db,
            user_id=user_id,
            input_image_id=input_image_id,
            output_image_id=output_image.id,
            title=product_name,
            ad_type="poster" if poster else "image",
            prompt=prompt_for_db,
            generated_text=result.copy_text,
            style=style.value,
            status="completed",
            commit=False,
        )
        history = create_history(
            db,
            user_id=user_id,
            advertisement_id=advertisement.id,
            action_type=action_type,
            status="completed",
            request_data=request_data,
            response_data=json.dumps(result.model_dump(mode="json"), ensure_ascii=False),
            commit=False,
        )
        db.commit()
        return history.id
    except Exception:
        db.rollback()
        raise


def _find_source_history_by_asset_id(
    db: Session,
    *,
    user_id: int,
    asset_id: str,
) -> History | None:
    return (
        db.query(History)
        .filter(
            History.user_id == user_id,
            History.status == "completed",
            History.response_data.contains(asset_id),
        )
        .order_by(History.created_at.desc())
        .first()
    )


@router.post("/style", response_model=StyleResponse)
def decide_style(
    req: StyleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StyleResponse:
    """스타일 결정 2경로 진입점 (경로1: 추천 / 경로2: 자유 텍스트)."""
    try:
        image_path: str | None = None
        if req.image_id is not None:
            row = get_image_by_id(db, req.image_id)
            if row is None or not row.file_path or not Path(row.file_path).is_file():
                raise HTTPException(status_code=404, detail=f"업로드 이미지 없음: image_id={req.image_id}")
            if row.user_id != current_user.id:
                raise HTTPException(status_code=403, detail="이미지 소유자만 스타일을 분석할 수 있습니다")
            image_path = row.file_path

        # user_id/tags 를 트레이스에 태그 — Langfuse UI 에서 사용자별·기능별(ads.style) 필터링용.
        with propagate_attributes(user_id=str(current_user.id), tags=["ads.style"]):
            return style_service.decide_style(req, image_path=image_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/generate", response_model=GenerateAdResponse)
def generate_ad(
    image: Optional[UploadFile] = File(None),
    image_id: Optional[int] = Form(None),
    product_name: str = Form(...),
    product_description: str = Form(""),
    style: Optional[StylePreset] = Form(None),
    template_id: Optional[str] = Form(None),  # TEMPLATE-PIPE-V2: 카탈로그 연출 레시피 id
    extra_request: str = Form(""),            # 템플릿 생성 시 사용자 추가 연출 요청(선택)
    use_vision: bool = Form(False),
    poster: bool = Form(False),
    seed: Optional[int] = Form(None),
    purpose: AdPurpose = Form(AdPurpose.SNS),
    sizes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerateAdResponse:
    """통합 광고 생성: 입력 → 전처리 → 배경 생성+조화 → 문구 (→ 포스터 오버레이).

    이미지 입력 2방식 (둘 중 하나 필수):
      - image    : 직접 파일 업로드 (단독 호출)
      - image_id : /images/upload (PR #14) 로 업로드된 DB 이미지 참조
    실행 위치: settings.GENERATION_SERVICE_URL 있으면 GPU 서비스 HTTP 호출(배포 B),
      없으면 로컬 실행(모놀리식). warm 약 20초 — 프론트 timeout 여유(60s+) 필요.
    """
    current_user_id = current_user.id
    input_image_id: Optional[int] = None
    temporary_source_path: Path | None = None
    # 계약: template_id 없으면 style 필수(기존), 있으면 서버측 연출 레시피로 생성(style 무시).
    if template_id is None and style is None:
        raise HTTPException(status_code=422, detail="style 또는 template_id 중 하나가 필요합니다")
    request_data = json.dumps(
        {
            "image_id": image_id,
            "filename": image.filename if image else None,
            "product_name": product_name,
            "product_description": product_description,
            "style": style.value if style else None,
            "template_id": template_id,
            "extra_request": extra_request or None,
            "use_vision": use_vision,
            "poster": poster,
            "seed": seed,
            "purpose": purpose.value,
            "sizes": sizes,
        },
        ensure_ascii=False,
    )

    if image_id is not None:
        row = get_image_by_id(db, image_id)
        if row is None or not row.file_path or not Path(row.file_path).is_file():
            raise HTTPException(status_code=404, detail=f"업로드 이미지 없음: image_id={image_id}")
        if row.user_id != current_user_id:
            raise HTTPException(status_code=403, detail="이미지 소유자만 광고를 생성할 수 있습니다")
        src_path = Path(row.file_path)
        input_image_id = row.id
    elif image is not None:
        _, suffix, content = read_image_upload_file_sync(image)
        TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        temporary_source_path = TEMP_UPLOAD_DIR / f"{uuid.uuid4().hex[:12]}{suffix}"
        src_path = temporary_source_path
        src_path.write_bytes(content)
    else:
        raise HTTPException(status_code=400, detail="image 파일 또는 image_id 중 하나가 필요합니다")

    product = ProductInfo(name=product_name, description=product_description or None)
    if template_id is not None:
        prompt_for_db = json.dumps({"template_id": template_id}, ensure_ascii=False)  # 프롬프트 본문 미저장(서버측 전용)
    else:
        prompt = build_image_prompt(product, style)
        prompt_for_db = json.dumps(
            {"positive": prompt.positive, "negative": prompt.negative},
            ensure_ascii=False,
        )
    credit_type = _consume_generation_credit(db, current_user_id)

    try:
        # user_id/tags 를 트레이스에 태그 — 사용자별 비용·품질을 Langfuse 에서 필터링할 수 있게.
        # (원격 GPU 서비스 경로는 별도 프로세스라 이 컨텍스트가 넘어가지 않고, 그쪽 프로세스가
        #  자체적으로 트레이싱한다 — generation_client.is_remote() 분기 참고.)
        with propagate_attributes(user_id=str(current_user_id), tags=["ads.generate"]):
            if template_id is not None:
                # TEMPLATE-PIPE-V2: 카탈로그 연출 레시피 + identity_grade 보존 (서버측 프롬프트)
                out = template_generation.generate_from_template(
                    str(src_path), template_id, product, use_vision=use_vision,
                    extra_request=extra_request,
                )
                result = _to_response(out)
            elif generation_client.is_remote():
                result = generation_client.generate_remote(
                    str(src_path), product, style, seed, use_vision, poster, purpose
                )
            else:
                out = generation_service.run_from_upload_v2(
                    str(src_path), product, style, seed, use_vision, poster
                )
                result = _to_response(out)

        if template_id is None and purpose == AdPurpose.BANNER:
            requested_sizes = [value.strip() for value in sizes.split(",") if value.strip()]
            result = _compose_banner_response(result, product_name, requested_sizes or None)
        elif template_id is None and purpose in (AdPurpose.CARD_NEWS, AdPurpose.DETAIL_PAGE):
            if not generation_client.is_remote():
                raise ValueError("카드뉴스·상세페이지는 GPU 생성 서비스 연결이 필요합니다")

        history_id = _record_generated_result(
            user_id=current_user_id,
            db=db,
            input_image_id=input_image_id,
            product_name=product_name,
            style=result.style,
            action_type="ads.generate",
            poster=poster,
            prompt_for_db=prompt_for_db,
            result=result,
            request_data=request_data,
        )
        return result.model_copy(update={"history_id": history_id})
    except ValueError as e:
        _restore_generation_credit(db, current_user_id, credit_type)
        create_history(
            db,
            user_id=current_user_id,
            action_type="ads.generate",
            status="failed",
            request_data=request_data,
            error_message=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        db.rollback()
        _restore_generation_credit(db, current_user_id, credit_type)
        create_history(
            db,
            user_id=current_user_id,
            action_type="ads.generate",
            status="failed",
            request_data=request_data,
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail=f"광고 생성 실패: {e}") from e
    finally:
        _remove_temporary_upload(temporary_source_path)


@router.post("/regenerate", response_model=GenerateAdResponse)
def regenerate_ad(
    req: RegenerateAdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerateAdResponse:
    """FR-12: 기존 전처리 산출물 재사용, 새 seed 로 재생성 (전처리 생략 → 더 빠름)."""
    if not generation_service.is_valid_asset_id(req.asset_id):
        raise HTTPException(status_code=400, detail=f"잘못된 asset_id 형식: {req.asset_id}")

    current_user_id = current_user.id
    request_data = json.dumps(req.model_dump(mode="json"), ensure_ascii=False)
    source_history = _find_source_history_by_asset_id(
        db,
        user_id=current_user_id,
        asset_id=req.asset_id,
    )
    if source_history is None:
        create_history(
            db,
            user_id=current_user_id,
            action_type="ads.regenerate",
            status="failed",
            request_data=request_data,
            error_message=f"재생성할 생성 이력 없음: asset_id={req.asset_id}",
        )
        raise HTTPException(status_code=404, detail="재생성할 생성 이력을 찾을 수 없습니다")

    input_image_id = (
        source_history.advertisement.input_image_id
        if source_history.advertisement is not None
        else None
    )
    product = ProductInfo(name=req.product_name, description=req.product_description)
    prompt = build_image_prompt(product, req.style)
    prompt_for_db = json.dumps(
        {"positive": prompt.positive, "negative": prompt.negative},
        ensure_ascii=False,
    )
    credit_type = _consume_generation_credit(db, current_user_id)
    try:
        with propagate_attributes(user_id=str(current_user_id), tags=["ads.regenerate"]):
            if generation_client.is_remote():
                result = generation_client.regenerate_remote(req.model_dump())
            else:
                out = generation_service.rerun_v2(
                    req.asset_id, product, req.style, req.prev_seed, req.use_vision, req.poster
                )
                result = _to_response(out)

        if req.purpose == AdPurpose.BANNER:
            result = _compose_banner_response(
                result, req.product_name or "상품", req.sizes or None
            )
        elif req.purpose != AdPurpose.SNS:
            raise ValueError("상세페이지·카드뉴스는 5구도 생성 API 연결 후 사용할 수 있습니다")

        history_id = _record_generated_result(
            db=db,
            user_id=current_user_id,
            input_image_id=input_image_id,
            product_name=req.product_name,
            style=req.style,
            poster=req.poster,
            prompt_for_db=prompt_for_db,
            result=result,
            action_type="ads.regenerate",
            request_data=request_data,
        )
        return result.model_copy(update={"history_id": history_id})
    except ValueError as e:
        _restore_generation_credit(db, current_user_id, credit_type)
        create_history(
            db,
            user_id=current_user_id,
            action_type="ads.regenerate",
            status="failed",
            request_data=request_data,
            error_message=str(e),
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        _restore_generation_credit(db, current_user_id, credit_type)
        create_history(
            db,
            user_id=current_user_id,
            action_type="ads.regenerate",
            status="failed",
            request_data=request_data,
            error_message=str(e),
        )
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        db.rollback()
        _restore_generation_credit(db, current_user_id, credit_type)
        create_history(
            db,
            user_id=current_user_id,
            action_type="ads.regenerate",
            status="failed",
            request_data=request_data,
            error_message=str(e),
        )
        raise HTTPException(status_code=500, detail=f"재생성 실패: {e}") from e


@router.get("/image/{filename}")
def get_result_image(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """현재 사용자가 소유한 생성 결과 이미지만 반환한다."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="잘못된 파일명")

    image = (
        db.query(Image)
        .filter(
            Image.user_id == current_user.id,
            Image.image_type == "generated",
            Image.stored_filename == filename,
        )
        .order_by(Image.id.desc())
        .first()
    )
    if image is None or not image.file_path:
        raise HTTPException(status_code=404, detail="이미지 없음")

    results_dir = image_service.RESULTS_DIR.resolve()
    path = Path(image.file_path).resolve()
    try:
        path.relative_to(results_dir)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="이미지 없음") from exc
    if path.name != filename or not path.is_file():
        raise HTTPException(status_code=404, detail="이미지 없음")
    return FileResponse(path, media_type=image.content_type or "image/png")


# --- 템플릿 서비스 (DIRECTION_v6 T4) -----------------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


@router.get("/templates")
def list_ad_templates(
    target: Optional[str] = None,
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """템플릿 프리셋 목록. 원장은 app/templates/templates.yaml (신규 템플릿 = YAML 추가).

    프론트는 선택 템플릿의 style_preset·knob 을 기존 POST /ads/generate 폼에 그대로 실어
    보낸다 — 생성 계약은 그대로, 이 목록은 읽기 전용 메타데이터다.
    """
    items = template_service.list_templates(target)
    for item in items:
        item["thumbnail"] = (
            f"{settings.API_PREFIX}/ads/template-thumb/{item['id']}"
            if item.get("thumbnail") else None)
    return items


@router.get("/template-thumb/{template_id}")
def get_template_thumbnail(
    template_id: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """템플릿 정적 썸네일. 경로는 검증된 원장 값(assets/templates)만 — 사용자 입력 경로 아님."""
    try:
        preset = template_service.get_template(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="미지 템플릿") from exc
    if not preset.thumbnail:
        raise HTTPException(status_code=404, detail="썸네일 없음")
    path = (_BACKEND_ROOT / preset.thumbnail).resolve()
    try:
        path.relative_to((_BACKEND_ROOT / "assets" / "templates").resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="썸네일 없음") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="썸네일 없음")
    return FileResponse(path, media_type="image/png")
