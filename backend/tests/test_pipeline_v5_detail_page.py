from pathlib import Path
from PIL import Image
import pytest
from app.schemas.ads import AdPurpose
from app.services.pipeline_v5 import generate_v5
from app.services.pipeline_v5.formats.detail_page import DEFAULT_CTA_LABEL, DEFAULT_CTA_TITLE
from app.services.pipeline_v5.hero import DetailCut, DetailCutRole, hero_from_existing


def _paths(tmp_path, count=5):
    result = []
    for i in range(count):
        path = tmp_path / f"cut_{i}.png"
        image = Image.new("RGB", (800, 900), (235, 235, 235))
        # 역할별 피사체 위치·형태가 달라 구조 유사도 게이트를 통과하는 fixture.
        from PIL import ImageDraw
        draw = ImageDraw.Draw(image)
        draw.ellipse((40 + i * 120, 80 + i * 90, 220 + i * 120, 300 + i * 90), fill=(60 + i * 25, 90, 120))
        draw.rectangle((i * 70, 650 - i * 80, 260 + i * 70, 780 - i * 80), fill=(120, 60 + i * 20, 80))
        image.save(path)
        result.append(str(path))
    return result


def _cuts(paths):
    return tuple(DetailCut(path, role) for path, role in zip(paths, DetailCutRole))


def _render(tmp_path, cuts):
    hero = hero_from_existing(cuts[0].image_path, headline="시그니처 라떼", detail_cuts=cuts)
    return generate_v5(cuts[0].image_path, "라떼", purpose=AdPurpose.DETAIL_PAGE,
                       hero_asset=hero, output_dir=str(tmp_path / "out"))


def test_detail_page_requires_named_camera_roles(tmp_path):
    paths = _paths(tmp_path)
    hero = hero_from_existing(paths[0], detail_image_paths=tuple(paths[1:]))
    with pytest.raises(ValueError, match="구도 역할"):
        generate_v5(paths[0], "상품", purpose=AdPurpose.DETAIL_PAGE,
                    hero_asset=hero, output_dir=str(tmp_path / "out"))


def test_missing_role_is_rejected(tmp_path):
    cuts = _cuts(_paths(tmp_path))[:-1]
    with pytest.raises(ValueError, match="lifestyle"):
        _render(tmp_path, cuts)


def test_duplicate_role_is_rejected(tmp_path):
    paths = _paths(tmp_path, 6)
    cuts = _cuts(paths[:5]) + (DetailCut(paths[5], DetailCutRole.HERO),)
    with pytest.raises(ValueError, match="역할이 중복"):
        _render(tmp_path, cuts)


def test_duplicate_content_cannot_claim_another_role(tmp_path):
    paths = _paths(tmp_path)
    duplicate = tmp_path / "duplicate.png"
    duplicate.write_bytes(Path(paths[0]).read_bytes())
    cuts = list(_cuts(paths))
    cuts[-1] = DetailCut(str(duplicate), DetailCutRole.LIFESTYLE)
    with pytest.raises(ValueError, match="같은 이미지 내용"):
        _render(tmp_path, tuple(cuts))


def test_visually_similar_framing_is_rejected_even_when_files_differ(tmp_path):
    paths = _paths(tmp_path)
    original = Image.open(paths[0]).convert("RGB")
    shifted = tmp_path / "same_framing_brighter.png"
    original.point(lambda value: min(255, value + 5)).save(shifted)
    cuts = list(_cuts(paths))
    cuts[-1] = DetailCut(str(shifted), DetailCutRole.LIFESTYLE)
    with pytest.raises(ValueError, match="구도가 너무 유사"):
        _render(tmp_path, tuple(cuts))


def test_five_roles_render_sales_page(tmp_path):
    result = _render(tmp_path, _cuts(_paths(tmp_path)))
    image = Image.open(result.outputs[0])
    assert image.width == 860 and image.height >= 4000


def test_internal_gate_language_never_leaks_into_customer_copy():
    assert DEFAULT_CTA_TITLE == "지금 만나보세요"
    assert DEFAULT_CTA_LABEL == "자세히 보기"
    assert "다섯" not in DEFAULT_CTA_TITLE and "5컷" not in DEFAULT_CTA_TITLE
