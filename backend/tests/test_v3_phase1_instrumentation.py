import json
from contextlib import contextmanager
from types import SimpleNamespace

from app.harness.run_logger import RunLogger
from app.services import generation_service, gpt_service


def test_run_logger_records_stages_metadata_and_usage(tmp_path, monkeypatch):
    runs_path = tmp_path / "runs.jsonl"
    monkeypatch.setattr(gpt_service, "API_USAGE_LOG", [])

    with RunLogger(
        phase="V3P1", mode="pending", engine="pending",
        input="latte.png", runs_path=runs_path,
    ) as run:
        with run.stage("analysis"):
            gpt_service.API_USAGE_LOG.append(
                gpt_service.ApiUsage("analyze_menu", 120, 30, 150)
            )
        run.set_meta(mode="food", engine="style:monotone", seed=42, timing="ignored")
        run.set_output("result.png")

    record = json.loads(runs_path.read_text(encoding="utf-8"))
    assert record["mode"] == "food"
    assert record["engine"] == "style:monotone"
    assert record["seed"] == 42
    assert record["timing"]["total_s"] >= 0
    assert record["timing"] != "ignored"
    assert "analysis" in record["stages"]
    assert record["metrics"]["openai_calls"] == 1
    assert record["metrics"]["openai_tokens"] == 150
    assert record["llm_usage"][0]["label"] == "analyze_menu"


def test_analyze_menu_caches_successful_name_analysis(monkeypatch):
    calls = 0

    def fake_chat(_messages, label):
        nonlocal calls
        calls += 1
        assert label == "analyze_menu"
        return {
            "domain": "food", "category": "default", "subject_en": "cafe latte",
            "core_ingredients": ["espresso", "milk"], "texture_hero": False,
            "material": "default", "food_mode": "cafe", "lang": "ko",
        }

    gpt_service.analyze_menu.cache_clear()
    monkeypatch.setattr(gpt_service, "_chat_json", fake_chat)
    try:
        first = gpt_service.analyze_menu("카페라떼")
        second = gpt_service.analyze_menu("카페라떼")
    finally:
        gpt_service.analyze_menu.cache_clear()

    assert first is second
    assert calls == 1


def test_process_ad_records_full_pipeline_stages_without_eval(tmp_path, monkeypatch):
    events = []

    class FakeRun:
        def __init__(self, **kwargs):
            events.append(("init", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @contextmanager
        def stage(self, name):
            events.append(("stage", name))
            yield

        def set_meta(self, **kwargs):
            events.append(("meta", kwargs))

        def set_output(self, path):
            events.append(("output", path))

        def add_metric(self, key, value):
            events.append(("metric", key, value))

    import app.harness.run_logger as run_logger_module
    from app.harness import metrics
    from app.services import style_gen

    source = tmp_path / "latte.png"
    source.write_bytes(b"source")
    generated = tmp_path / "generated.png"

    monkeypatch.setattr(run_logger_module, "RunLogger", FakeRun)
    monkeypatch.setattr(
        gpt_service, "analyze_menu",
        lambda _name: SimpleNamespace(subject_en="cafe latte", domain="food", food_mode="cafe"),
    )

    def fake_generate(*_args, **_kwargs):
        generated.write_bytes(b"result")
        return str(generated)

    monkeypatch.setattr(style_gen, "generate_scene", fake_generate)
    monkeypatch.setattr(
        generation_service, "_generate_copy",
        lambda *_args, **_kwargs: SimpleNamespace(copy_text="headline\nsubcopy"),
    )
    monkeypatch.delenv("ADNOVA_EVAL", raising=False)
    monkeypatch.setattr(
        metrics, "aesthetic_primary",
        lambda _path: (_ for _ in ()).throw(AssertionError("evaluation must be opt-in")),
    )

    result = generation_service.process_ad(
        str(source), "카페라떼", style="monotone", poster=False,
        output_dir=str(tmp_path), seed=42,
    )

    stages = [event[1] for event in events if event[0] == "stage"]
    assert stages == ["analysis", "generate", "select", "copy"]
    assert result.seed == 42
    assert result.aesthetic is None
    assert any(event[0] == "meta" and event[1]["engine"] == "style:monotone"
               for event in events)
    assert any(event[0] == "output" and event[1].endswith("_s42.png") for event in events)


def test_eval_device_auto_uses_torch_availability(monkeypatch):
    from app.harness import metrics

    monkeypatch.delenv("ADNOVA_EVAL_DEVICE", raising=False)
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    assert metrics._eval_device() == "cpu"


def test_v2_request_ledger_includes_gate_generation_and_platform_copy(tmp_path, monkeypatch):
    import app.harness.run_logger as run_logger_module
    from app.schemas.ads import ProductInfo, StylePreset
    from app.services import image_service

    runs_path = tmp_path / "runs.jsonl"
    processed_dir = tmp_path / "processed"
    results_dir = tmp_path / "results"
    processed_dir.mkdir()
    results_dir.mkdir()
    source = tmp_path / "upload.png"
    source.write_bytes(b"input")

    real_logger = RunLogger
    monkeypatch.setattr(
        run_logger_module, "RunLogger",
        lambda **kwargs: real_logger(**kwargs, runs_path=runs_path),
    )
    monkeypatch.setattr(image_service, "PROCESSED_DIR", processed_dir)
    monkeypatch.setattr(image_service, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(gpt_service, "API_USAGE_LOG", [])

    def add_usage(label):
        gpt_service.API_USAGE_LOG.append(gpt_service.ApiUsage(label, 100, 20, 120))

    def fake_gate(*_args):
        add_usage("verify_photo_subject")
        return {"match": True, "seen": "latte"}

    def fake_process(_path, _name, **kwargs):
        with kwargs["_run"].stage("generate"):
            add_usage("analyze_menu")
            add_usage("generate_copy/blip")
            output = results_dir / "result.png"
            output.write_bytes(b"result")
        return SimpleNamespace(
            final_image_path=str(output), seed=42, copy_text="copy", seconds=1.0,
            domain="food", engine="style:monotone", subject_en="cafe latte",
        )

    def fake_platform(*_args):
        add_usage("platform_copy")
        return {}

    monkeypatch.setattr(gpt_service, "verify_photo_subject", fake_gate)
    monkeypatch.setattr(generation_service, "process_ad", fake_process)
    monkeypatch.setattr(generation_service, "_platform_copies_safe", fake_platform)

    generation_service.run_from_upload_v2(
        str(source), ProductInfo(name="카페라떼"), StylePreset.MONOTONE,
    )

    record = json.loads(runs_path.read_text(encoding="utf-8"))
    assert set(record["stages"]) >= {"input_gate", "input_prepare", "generate", "platform_copy"}
    assert record["metrics"]["openai_calls"] == 4
    assert record["metrics"]["openai_tokens"] == 480
    assert record["timing"]["total_s"] >= 0
