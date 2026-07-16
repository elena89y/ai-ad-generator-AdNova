"""v4.1 P4A 통합 Vision 분석·asset 캐시·호출수 계약 회귀 테스트."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.harness.run_logger import RunLogger
from app.schemas.ads import ProductInfo, StylePreset
from app.services import generation_service, gpt_service, image_service, router


ASSET_ID = "abc123def456"


def _analysis(**overrides) -> gpt_service.PhotoAnalysis:
    values = {
        "match": True,
        "seen": "흰 컵의 카페라떼",
        "domain": "food",
        "display_name": "카페라떼",
        "subject_en": "cafe latte",
        "category": "default",
        "core_ingredients": ["espresso", "milk"],
        "texture_hero": False,
        "material": "default",
        "food_mode": "cafe",
        "lang": "ko",
        "container_kind": "cup",
        "container_color": "white",
        "container_opacity": "opaque",
        "temperature": "hot",
        "view_angle": "eye",
        "visible_text": "",
    }
    values.update(overrides)
    return gpt_service.PhotoAnalysis(**values)


def _install_run_logger(monkeypatch, runs_path):
    import app.harness.run_logger as run_logger_module

    monkeypatch.setattr(
        run_logger_module,
        "RunLogger",
        lambda **kwargs: RunLogger(**kwargs, runs_path=runs_path),
    )


def _add_usage(label: str) -> None:
    gpt_service.API_USAGE_LOG.append(gpt_service.ApiUsage(label, 10, 2, 12))


def _fake_process(results_dir, labels: tuple[str, ...] = ("generate_copy/blip",)):
    def run(_path, _name, **kwargs):
        for label in labels:
            _add_usage(label)
        output = results_dir / "result.png"
        output.write_bytes(b"result")
        analysis = kwargs.get("analysis")
        return SimpleNamespace(
            final_image_path=str(output), seed=kwargs["seed"], copy_text="copy", seconds=1.0,
            domain=getattr(analysis, "domain", "food"), engine="style:monotone",
            subject_en=getattr(analysis, "subject_en", "cafe latte"),
        )

    return run


def test_analyze_photo_parses_schema_and_preserves_menu_compatibility(monkeypatch):
    monkeypatch.setattr(gpt_service, "_vision_part", lambda path: {"image": path})

    def fake_chat(messages, label):
        assert label == "analyze_photo"
        assert messages[0]["content"][1] == {"image": "latte.png"}
        return {
            "match": "false",
            "seen": "흰 컵의 카페라떼",
            "domain": "food",
            "display_name": "ignored",
            "subject_en": "Cafe Latte",
            "category": "default",
            "core_ingredients": ["Espresso", "Milk"],
            "texture_hero": "false",
            "material": "default",
            "food_mode": "cafe",
            "lang": "ko",
            "container_kind": "Cup",
            "container_color": "White",
            "container_opacity": "opaque",
            "temperature": "hot",
            "view_angle": "eye",
            "visible_text": "CAFE",
        }

    monkeypatch.setattr(gpt_service, "_chat_json", fake_chat)

    result = gpt_service.analyze_photo("latte.png", "카페라떼")

    assert result is not None
    assert result.match is False
    assert result.texture_hero is False
    assert result.display_name == "카페라떼"
    assert result.subject_en == "Cafe Latte"
    assert result.food_en == result.subject_en
    assert result.core_ingredients == ["espresso", "milk"]
    assert result.container_kind == "cup"
    assert result.visible_text == "CAFE"


def test_analyze_photo_parse_failure_returns_none(monkeypatch):
    monkeypatch.setattr(gpt_service, "_vision_part", lambda _path: {})
    monkeypatch.setattr(gpt_service, "_chat_json", lambda *_args, **_kwargs: {"match": True})

    assert gpt_service.analyze_photo("broken.png", "상품") is None


def test_analyze_photo_vision_read_failure_returns_none(monkeypatch):
    monkeypatch.setattr(
        gpt_service,
        "_vision_part",
        lambda _path: (_ for _ in ()).throw(OSError("missing image")),
    )
    monkeypatch.setattr(
        gpt_service,
        "_chat_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not call API")),
    )

    assert gpt_service.analyze_photo("missing.png", "상품") is None


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("subject_en", "카페라떼"),
        ("core_ingredients", ["우유"]),
        ("container_kind", "유리컵"),
        ("container_color", "투명"),
    ],
)
def test_analyze_photo_rejects_non_ascii_prompt_fields(monkeypatch, field, invalid):
    payload = {
        "match": True,
        "seen": "흰 컵의 카페라떼",
        "domain": "food",
        "display_name": "ignored",
        "subject_en": "cafe latte",
        "category": "default",
        "core_ingredients": ["espresso", "milk"],
        "texture_hero": False,
        "material": "default",
        "food_mode": "cafe",
        "lang": "ko",
        "container_kind": "cup",
        "container_color": "clear",
        "container_opacity": "transparent",
        "temperature": "hot",
        "view_angle": "eye",
        "visible_text": "카페",
    }
    payload[field] = invalid
    monkeypatch.setattr(gpt_service, "_vision_part", lambda _path: {})
    monkeypatch.setattr(gpt_service, "_chat_json", lambda *_args, **_kwargs: payload)

    assert gpt_service.analyze_photo("latte.png", "카페라떼") is None


def test_photo_analysis_cache_roundtrip_and_corruption_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "PROCESSED_DIR", tmp_path)
    expected = _analysis(visible_text="CAFE 24")

    assert generation_service._save_photo_analysis(ASSET_ID, expected) is True
    assert generation_service._load_photo_analysis(ASSET_ID) == expected

    cache_path = tmp_path / f"{ASSET_ID}_analysis.json"
    cache_path.write_text("{broken", encoding="utf-8")
    assert generation_service._load_photo_analysis(ASSET_ID) is None

    invalid = json.loads(json.dumps(expected.__dict__, ensure_ascii=False))
    invalid["container_color"] = "흰색"
    cache_path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
    assert generation_service._load_photo_analysis(ASSET_ID) is None


def test_initial_unified_request_records_three_calls_and_saves_cache(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    results_dir = tmp_path / "results"
    processed_dir.mkdir()
    results_dir.mkdir()
    source = tmp_path / "upload.png"
    source.write_bytes(b"input")
    runs_path = tmp_path / "runs.jsonl"
    expected = _analysis()

    monkeypatch.setenv("UNIFIED_ANALYSIS", "1")
    monkeypatch.setattr(image_service, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(image_service, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(gpt_service, "API_USAGE_LOG", [])
    _install_run_logger(monkeypatch, runs_path)

    def fake_analysis(*_args):
        _add_usage("analyze_photo")
        return expected

    monkeypatch.setattr(gpt_service, "analyze_photo", fake_analysis)
    monkeypatch.setattr(
        gpt_service,
        "verify_photo_subject",
        lambda *_args: (_ for _ in ()).throw(AssertionError("legacy gate must not run")),
    )

    captured = {}

    def fake_process(*args, **kwargs):
        captured["analysis"] = kwargs["analysis"]
        return _fake_process(results_dir)(*args, **kwargs)

    def fake_platform(_product, _style, analysis):
        captured["platform_analysis"] = analysis
        _add_usage("platform_copy")
        return {}

    monkeypatch.setattr(generation_service, "process_ad", fake_process)
    monkeypatch.setattr(generation_service, "_platform_copies_safe", fake_platform)

    result = generation_service.run_from_upload_v2(
        str(source), ProductInfo(name="카페라떼"), StylePreset.MONOTONE,
    )

    record = json.loads(runs_path.read_text(encoding="utf-8"))
    cached = generation_service._load_photo_analysis(result.asset_id)
    assert cached == expected
    assert captured == {"analysis": expected, "platform_analysis": expected}
    assert record["phase"] == "V4P4A"
    assert record["metrics"]["openai_calls"] == 3
    assert [item["label"] for item in record["llm_usage"]] == [
        "analyze_photo", "generate_copy/blip", "platform_copy",
    ]


def test_unified_failure_falls_back_to_legacy_four_call_path(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    results_dir = tmp_path / "results"
    processed_dir.mkdir()
    results_dir.mkdir()
    source = tmp_path / "upload.png"
    source.write_bytes(b"input")
    runs_path = tmp_path / "runs.jsonl"

    monkeypatch.setenv("UNIFIED_ANALYSIS", "1")
    monkeypatch.setattr(image_service, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(image_service, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(gpt_service, "API_USAGE_LOG", [])
    _install_run_logger(monkeypatch, runs_path)
    monkeypatch.setattr(gpt_service, "analyze_photo", lambda *_args: None)

    def fake_gate(*_args):
        _add_usage("verify_photo_subject")
        return {"match": True, "seen": "latte"}

    captured = {}

    def fake_process(*args, **kwargs):
        captured["analysis"] = kwargs["analysis"]
        return _fake_process(results_dir, ("analyze_menu", "generate_copy/blip"))(*args, **kwargs)

    def fake_platform(_product, _style, analysis):
        captured["platform_analysis"] = analysis
        _add_usage("platform_copy")
        return {}

    monkeypatch.setattr(gpt_service, "verify_photo_subject", fake_gate)
    monkeypatch.setattr(generation_service, "process_ad", fake_process)
    monkeypatch.setattr(generation_service, "_platform_copies_safe", fake_platform)

    result = generation_service.run_from_upload_v2(
        str(source), ProductInfo(name="카페라떼"), StylePreset.MONOTONE,
    )

    record = json.loads(runs_path.read_text(encoding="utf-8"))
    assert captured == {"analysis": None, "platform_analysis": None}
    assert generation_service._load_photo_analysis(result.asset_id) is None
    assert record["metrics"]["openai_calls"] == 4
    assert [item["label"] for item in record["llm_usage"]] == [
        "verify_photo_subject", "analyze_menu", "generate_copy/blip", "platform_copy",
    ]


def test_cached_rerun_records_two_calls_without_analysis_request(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    results_dir = tmp_path / "results"
    processed_dir.mkdir()
    results_dir.mkdir()
    (processed_dir / f"{ASSET_ID}_v2input.png").write_bytes(b"input")
    runs_path = tmp_path / "runs.jsonl"
    expected = _analysis()

    monkeypatch.setenv("UNIFIED_ANALYSIS", "1")
    monkeypatch.setattr(image_service, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(image_service, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(gpt_service, "API_USAGE_LOG", [])
    monkeypatch.setattr(generation_service, "_next_seed", lambda _prev: 99)
    _install_run_logger(monkeypatch, runs_path)
    assert generation_service._save_photo_analysis(ASSET_ID, expected)
    monkeypatch.setattr(
        gpt_service,
        "analyze_photo",
        lambda *_args: (_ for _ in ()).throw(AssertionError("cached rerun must not analyze")),
    )

    captured = {}

    def fake_process(*args, **kwargs):
        captured["analysis"] = kwargs["analysis"]
        return _fake_process(results_dir)(*args, **kwargs)

    def fake_platform(_product, _style, analysis):
        captured["platform_analysis"] = analysis
        _add_usage("platform_copy")
        return {}

    monkeypatch.setattr(generation_service, "process_ad", fake_process)
    monkeypatch.setattr(generation_service, "_platform_copies_safe", fake_platform)

    generation_service.rerun_v2(
        ASSET_ID, ProductInfo(name="카페라떼"), StylePreset.MONOTONE, prev_seed=42,
    )

    record = json.loads(runs_path.read_text(encoding="utf-8"))
    assert captured == {"analysis": expected, "platform_analysis": expected}
    assert record["phase"] == "V4P4A"
    assert record["metrics"]["openai_calls"] == 2
    assert [item["label"] for item in record["llm_usage"]] == [
        "generate_copy/blip", "platform_copy",
    ]


def test_rerun_product_name_change_invalidates_cached_analysis(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    results_dir = tmp_path / "results"
    processed_dir.mkdir()
    results_dir.mkdir()
    (processed_dir / f"{ASSET_ID}_v2input.png").write_bytes(b"input")
    old_analysis = _analysis()
    new_analysis = _analysis(
        display_name="딸기 스무디",
        subject_en="strawberry smoothie",
        core_ingredients=["strawberry", "milk"],
        temperature="iced",
    )

    monkeypatch.setenv("UNIFIED_ANALYSIS", "1")
    monkeypatch.setattr(image_service, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(image_service, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(generation_service, "_next_seed", lambda _prev: 99)
    assert generation_service._save_photo_analysis(ASSET_ID, old_analysis)
    calls = 0
    captured = {}

    def fake_analysis(*_args):
        nonlocal calls
        calls += 1
        return new_analysis

    def fake_process(*args, **kwargs):
        captured["analysis"] = kwargs["analysis"]
        return _fake_process(results_dir)(*args, **kwargs)

    monkeypatch.setattr(gpt_service, "analyze_photo", fake_analysis)
    monkeypatch.setattr(generation_service, "process_ad", fake_process)
    monkeypatch.setattr(generation_service, "_platform_copies_safe", lambda *_args: {})

    generation_service.rerun_v2(
        ASSET_ID, ProductInfo(name="딸기 스무디"), StylePreset.MONOTONE, prev_seed=42,
    )

    assert calls == 1
    assert captured["analysis"] == new_analysis
    assert generation_service._load_photo_analysis(ASSET_ID) == new_analysis


def test_legacy_asset_rerun_analyzes_once_and_creates_cache(tmp_path, monkeypatch):
    processed_dir = tmp_path / "processed"
    results_dir = tmp_path / "results"
    processed_dir.mkdir()
    results_dir.mkdir()
    (processed_dir / f"{ASSET_ID}_v2input.png").write_bytes(b"input")
    expected = _analysis()

    monkeypatch.setenv("UNIFIED_ANALYSIS", "1")
    monkeypatch.setattr(image_service, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(image_service, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(generation_service, "_next_seed", lambda _prev: 99)
    monkeypatch.setattr(generation_service, "process_ad", _fake_process(results_dir))
    monkeypatch.setattr(generation_service, "_platform_copies_safe", lambda *_args: {})
    calls = 0

    def fake_analysis(*_args):
        nonlocal calls
        calls += 1
        return expected

    monkeypatch.setattr(gpt_service, "analyze_photo", fake_analysis)

    generation_service.rerun_v2(
        ASSET_ID, ProductInfo(name="카페라떼"), StylePreset.MONOTONE, prev_seed=42,
    )

    assert calls == 1
    assert generation_service._load_photo_analysis(ASSET_ID) == expected


def test_platform_copy_reuses_analysis_core_ingredients(monkeypatch):
    expected = _analysis(core_ingredients=["espresso", "milk"])
    captured = {}
    monkeypatch.setattr(
        gpt_service,
        "analyze_menu",
        lambda *_args: (_ for _ in ()).throw(AssertionError("analyze_menu must not run")),
    )

    def fake_platform(_product, _style, core_ingredients):
        captured["core"] = core_ingredients
        return {"instagram": {}}

    monkeypatch.setattr(gpt_service, "generate_platform_copy", fake_platform)

    result = generation_service._platform_copies_safe(
        ProductInfo(name="카페라떼"), StylePreset.MONOTONE, expected,
    )

    assert result == {"instagram": {}}
    assert captured["core"] == ["espresso", "milk"]


def test_process_ad_style_path_reuses_supplied_analysis(tmp_path, monkeypatch):
    from app.services import style_gen

    source = tmp_path / "latte.png"
    source.write_bytes(b"input")
    generated = tmp_path / "generated.png"
    expected = _analysis()
    monkeypatch.setattr(
        gpt_service,
        "analyze_menu",
        lambda *_args: (_ for _ in ()).throw(AssertionError("analyze_menu must not run")),
    )

    def fake_generate(*_args, **_kwargs):
        generated.write_bytes(b"result")
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)
    monkeypatch.setattr(
        generation_service,
        "_generate_copy",
        lambda *_args, **_kwargs: SimpleNamespace(copy_text="headline\nsubcopy"),
    )

    result = generation_service.process_ad(
        str(source), "카페라떼", style="monotone", poster=False, log=False,
        output_dir=str(tmp_path), seed=42, analysis=expected,
    )

    assert result.subject_en == "cafe latte"
    assert result.domain == "food"


def test_router_reuses_photo_material_without_second_vision_call(monkeypatch):
    from app.services import object_service

    expected = _analysis(
        domain="object", food_mode="dish", material="reflective",
        subject_en="perfume bottle", core_ingredients=[],
    )
    monkeypatch.setattr(
        gpt_service,
        "detect_material",
        lambda *_args: (_ for _ in ()).throw(AssertionError("second Vision call must not run")),
    )
    monkeypatch.setattr(
        object_service,
        "generate_object_ad",
        lambda *_args, **_kwargs: SimpleNamespace(output_path="object.png", seconds=1.0),
    )

    result = router.process_input("perfume.png", "향수", analysis=expected)

    assert result.engine == "objectcut:reflective"
    assert result.subject_en == "perfume bottle"
