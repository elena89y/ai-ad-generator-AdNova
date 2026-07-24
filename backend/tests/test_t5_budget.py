"""RETOUCH-003-2 — Kontext 지시문 T5 512토큰 예산 회귀 가드.

FLUX Kontext의 T5 인코더는 max_sequence_length=512로 초과분을 **뒤에서부터 조용히
버린다**. 조립 순서가 잠금→씬 지시라서 초과 시 팔레트·소품·피니시·no-logo 가드가
먼저 유실된다 — 2026-07-24 GPU 실측: 이상화 디저트 3/3에서 팔레트 소실·우드 테이블
폴백, 에디토리얼 우드 편차 3회의 유력 원인도 동일 기전(food_dessert 락 단독 544토큰).

이 테스트는 실제 T5 토크나이저(google/t5-v1_1-base, FLUX와 동일 SentencePiece 계열)로
전 스타일 × serving_type × 시드 조합의 지시문이 예산 안임을 고정한다. 토크나이저를
받을 수 없는 환경(오프라인 첫 실행)에서는 skip — 로컬 개발 머신에는 캐시가 있다.
"""
import pytest

from app.services.reference_style_plans import build_reference_instruction

transformers = pytest.importorskip("transformers")

_BUDGET = 512

_CASES = [
    # (serving_type, subject, core_ingredients) — 디저트/짭짤/면류(보강절 최장 경로)
    ("dessert", "blueberry fresh cream cake", ["blueberry", "fresh cream", "cake"]),
    ("dessert", "strawberry chocolate cream cake", ["strawberry", "chocolate", "cream"]),  # RETOUCH-004 초코 스왑 경로
    ("bakery", "butter red bean bread", ["butter", "red bean"]),
    ("dish", "grilled beef", None),
    ("dish", "cream carbonara pasta", ["pasta", "cream", "bacon", "parmesan"]),
]


@pytest.fixture(scope="module")
def t5_tok():
    try:
        return transformers.AutoTokenizer.from_pretrained("google/t5-v1_1-base", legacy=False)
    except Exception as exc:  # 네트워크·캐시 부재 — 예산 검증은 개발 머신에서만
        pytest.skip(f"T5 tokenizer unavailable: {exc}")


@pytest.mark.parametrize("style", ["pop", "monotone", "pastel", "editorial", "realism"])
def test_instruction_fits_t5_budget(t5_tok, style):
    for serving_type, subject, core in _CASES:
        for seed in range(12):
            instr = build_reference_instruction(
                style, "food", subject, scene_seed=seed,
                serving_type=serving_type, core_ingredients=core)
            assert instr is not None
            n = len(t5_tok(instr).input_ids)
            assert n <= _BUDGET, (
                f"{style}/{serving_type}/{subject}/seed{seed}: {n} tokens > {_BUDGET} — "
                "씬 지시·가드가 뒤에서부터 잘린다. 잠금/변형 문구를 압축할 것.")
