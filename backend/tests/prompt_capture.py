"""T1 소프트코딩 게이트: gpt_service 프롬프트를 고정 입력으로 재현해 바이트 단위 캡처 — 담당: 한의정.

원칙(DIRECTION_v6 §T1): 프롬프트 문구는 실측으로 튜닝된 값이다. YAML 외부화 리팩토링은
"동작 불변 + 데이터 외부화"만 허용 — 뜻만 같게 바꾸는 것도 금지. 이를 기계로 강제하기 위해
리팩토링 **전** 코드로 golden/gpt_prompts.json 을 생성하고, 이후 모든 변경은 이 캡처 결과가
golden 과 dict 동일(=문자열 바이트 동일)해야 통과한다.

golden 재생성(프롬프트를 의도적으로 바꾸는 별도 실험을 머지할 때만):
    cd backend && ../.venv/bin/python -m tests.prompt_capture
"""
from __future__ import annotations

import json
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "gpt_prompts.json"

# 이미지 base64 는 프롬프트 문구가 아니므로 캡처에서 자리표시자로 치환(골든 비대화 방지).
_DATA_URL_RE = re.compile(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+")

# 파서를 통과하는 최소 유효 응답 — 라벨별. (파싱 실패해도 캡처는 되지만 경고 소음 방지)
_CANNED: dict[str, dict] = {
    "generate_copy/blip": {"copy": "골든 헤드라인\n골든 서브"},
    "generate_copy/vision": {"copy": "골든 헤드라인\n골든 서브"},
    "generate_sns_copy": {"caption": "cap", "hashtags": ["#tag"]},
    "platform_copy": {
        "instagram": {"headline": "h", "body": "b", "hashtags": ["#i"]},
        "facebook": {"headline": "h", "body": "b", "hashtags": []},
        "x": {"headline": "h", "body": "b", "hashtags": []},
        "threads": {"headline": "h", "body": "b", "hashtags": []},
        "claimed_ingredients": [],
    },
    "detail_copy": {
        "intro_headline": "오늘의 상큼함을 담다", "story_title": "수제 청으로 만든 한 잔",
        "story_body": "매일 아침 딸기를 손질해 청을 담급니다. 설탕은 줄이고 과육은 살렸습니다.",
        "benefit_bullets": ["수제 딸기청", "당일 제조", "생과육 가득"],
        "top_view_label": "위에서 본 한 잔", "closeup_caption": "과육이 그대로",
        "profile_title": "한 잔의\n밀도", "profile_caption": "바닥까지 가라앉지 않는 과육",
        "lifestyle_line": "오후를 깨우는 붉은 한 모금",
        "cta_title": "지금 맛보세요", "cta_label": "주문하기",
        "claimed_ingredients": ["strawberry"],
    },
    "judge_ad/vision": {"appetizing": 7, "realism": 7, "artifact_free": 7,
                        "composition": 7, "adherence": 7, "overall": 7, "reason": "ok"},
    "compare_ads/vision": {"winner": "first", "reason": "ok"},
    "judge_calibrated": {"style_match": 7, "execution": 7, "identity": 7,
                         "overall": 7, "improve": "ok"},
    "english_labels": {"name": "STRAWBERRY ADE", "phrase": "FRESH BERRY REFRESHMENT"},
    "section_labels": {"top_view_label": "플레이팅", "detail_title": "촉촉한\n속결",
                       "cta_title": "지금 주문", "cta_label": "자세히 보기"},
    "cake_recipe": {"plausible": True, "layers": ["Layer 1: sponge"], "top": "cream"},
    "analyze_menu": {"domain": "food", "category": "soup",
                     "subject_en": "korean spicy beef soup",
                     "core_ingredients": ["beef", "scallion"], "texture_hero": False,
                     "material": "default", "food_mode": "dish", "lang": "ko"},
    "analyze_photo": {"match": True, "seen": "라떼", "domain": "food", "display_name": "카페라떼",
                      "subject_en": "cafe latte", "category": "default",
                      "core_ingredients": ["espresso", "milk"], "texture_hero": False,
                      "material": "default", "food_mode": "cafe", "lang": "ko",
                      "container_kind": "cup", "container_color": "white",
                      "container_opacity": "opaque", "temperature": "hot",
                      "view_angle": "eye", "visible_text": "",
                      "identity_parts": ["coffee", "latte art"],
                      "flexible_parts": ["cup", "saucer"]},
    "verify_photo_subject": {"match": True, "seen": "치킨"},
    "detect_ingredients": {"items": [{"name": "연어", "name_en": "salmon", "x": 0.4, "y": 0.5}]},
    "detect_material": {"material": "matte"},
    "analyze_image_for_style": {"candidates": [{"preset": "monotone", "reason": "r"},
                                               {"preset": "pop", "reason": "r"}]},
}


def _norm(messages) -> list:  # noqa: ANN001
    """메시지 구조를 그대로 보존하되 이미지 data URL 만 자리표시자로 치환."""
    return json.loads(_DATA_URL_RE.sub("[IMG]", json.dumps(messages, ensure_ascii=False)))


def _fake_response(canned: dict):  # noqa: ANN202
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps(canned, ensure_ascii=False)))],
        usage=None,  # _record_usage 는 usage 없으면 경고만 남기고 통과
    )


def capture_all(tmp_dir: Path) -> dict[str, list]:
    """gpt_service 의 모든 프롬프트 사이트를 고정 입력으로 실행해 {사이트: 메시지들} 반환."""
    from PIL import Image

    from app.schemas.ads import AdPurpose, ProductInfo, StylePreset
    from app.services import gpt_service, judge_service

    img1 = str(tmp_dir / "p1.png")
    img2 = str(tmp_dir / "p2.png")
    Image.new("RGB", (4, 4), (200, 40, 40)).save(img1)
    Image.new("RGB", (4, 4), (40, 40, 200)).save(img2)

    product = ProductInfo(name="딸기 에이드", description="상큼한 수제 청으로 만든 시그니처")

    captured: dict[str, list] = {}
    site: list[str] = [""]  # 현재 캡처 중인 사이트 키 (recorder 가 참조)

    def _recording_chat_json(messages, label):  # noqa: ANN001
        captured.setdefault(site[0], []).append(_norm(messages))
        return _CANNED[label]

    class _FakeClient:
        """직접 client.chat.completions.create 를 부르는 함수(detect_material 등)용."""

        def __init__(self) -> None:
            self.canned: dict = {}
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kw):  # noqa: ANN003, ANN202
            captured.setdefault(site[0], []).append(_norm(kw["messages"]))
            return _fake_response(self.canned)

    fake_client = _FakeClient()

    @contextmanager
    def at(key: str):  # noqa: ANN201
        site[0] = key
        yield
        site[0] = ""

    def _raise(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        raise RuntimeError("snapshot: raw JSON 경로 강제")

    with patch.object(gpt_service, "_chat_json", _recording_chat_json), \
         patch.object(gpt_service, "_get_client", lambda: fake_client), \
         patch.object(gpt_service, "_caption_image", lambda _p: "a glass of strawberry ade"), \
         patch.object(judge_service, "structured_labels", _raise):

        with at("generate_copy/blip"):
            gpt_service.generate_copy(img1, product, StylePreset.POP, use_vision=False)
        with at("generate_copy/blip_retry"):
            gpt_service.generate_copy(img1, product, StylePreset.POP, use_vision=False,
                                      feedback="마침표 금지 위반")
        with at("generate_copy/vision"):
            gpt_service.generate_copy(img1, product, StylePreset.WARM_VINTAGE, use_vision=True)
        with at("generate_sns_copy"):
            gpt_service.generate_sns_copy(product, StylePreset.EDITORIAL, AdPurpose.SNS)
        with at("platform_copy"):
            gpt_service.generate_platform_copy(
                product, StylePreset.POP,
                core_ingredients=["strawberry", "sparkling water"],
                image_desc="strawberry ade in a glass")
        # 교정 재생성 분기는 순수 함수라 직접 캡처(문자열 그대로 저장)
        captured["platform_copy/correction"] = [gpt_service._platform_copy_instruction(
            "딸기 에이드 — 상큼한 수제 청으로 만든 시그니처", StylePreset.POP,
            ["strawberry", "sparkling water"], "strawberry ade in a glass", ["mint"])]
        with at("detail_copy"):
            gpt_service.generate_detail_copy(
                "딸기 에이드", "strawberry ade", "drink", "달콤한 한 잔",
                subcopy="수제 청의 상큼함", core_ingredients=["strawberry", "sparkling water"],
                style_key="pop", image_desc="strawberry ade in a glass")
        captured["detail_copy/correction"] = [gpt_service._detail_copy_instruction(
            "딸기 에이드 — strawberry ade", "발랄하고 에너지 넘치는 톤", "달콤한 한 잔",
            "수제 청의 상큼함", ["strawberry", "sparkling water"],
            "strawberry ade in a glass", ["mint"])]
        with at("judge_ad/plain"):
            gpt_service.judge_ad(img1)
        with at("judge_ad/ref"):
            gpt_service.judge_ad(img1, instruction="make it pop", ref_path=img2)
        with at("compare_ads"):
            gpt_service.compare_ads(img1, img2, ref_path=img2, debias=False)
        with at("judge_calibrated"):
            gpt_service.judge_ad_calibrated(img1, "pop", [img1, img2], extra="Focus on color.")
        with at("english_labels"):
            gpt_service.generate_english_labels(product)
        with at("section_labels"):
            gpt_service.generate_section_labels("딸기 에이드", "strawberry ade", "drink",
                                                "달콤한 한 잔")
        with at("cake_recipe"):
            gpt_service.build_cake_layers("딸기 생크림 케이크", "strawberry cream cake",
                                          image_desc="three tier cake")
        with at("analyze_menu"):
            gpt_service.analyze_menu.__wrapped__("육개장")  # lru_cache 우회
        with at("analyze_photo"):
            gpt_service.analyze_photo(img1, "카페라떼")
        with at("verify_photo_subject"):
            gpt_service.verify_photo_subject(img1, "치킨")
        with at("detect_ingredients"):
            gpt_service.detect_ingredients(img1, n=3)
        fake_client.canned = _CANNED["detect_material"]
        with at("detect_material"):
            gpt_service.detect_material(img1)
        fake_client.canned = _CANNED["analyze_image_for_style"]
        with at("analyze_image_for_style"):
            gpt_service.analyze_image_for_style(img1)

    # 프롬프트 데이터 dict 도 골든에 포함(값 변경 감지)
    captured["_STYLE_TONE"] = [{k.value: v for k, v in gpt_service._STYLE_TONE.items()}]
    captured["_PURPOSE_GUIDE"] = [{k.value: v for k, v in gpt_service._PURPOSE_GUIDE.items()}]
    captured["_PLATFORM_PERSONA"] = [dict(gpt_service._PLATFORM_PERSONA)]
    captured["_JUDGE_SYS"] = [gpt_service._JUDGE_SYS]
    return captured


def write_golden() -> Path:
    with tempfile.TemporaryDirectory() as td:
        data = capture_all(Path(td))
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")
    return GOLDEN_PATH


if __name__ == "__main__":
    print(f"golden 갱신: {write_golden()}")
