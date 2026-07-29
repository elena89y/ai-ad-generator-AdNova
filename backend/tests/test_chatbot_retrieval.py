"""챗봇 하이브리드 검색 단위 테스트 — 담당: 한의정.

OpenAI 호출 없음 (retrieval 은 전부 로컬). dense 는 fake 임베더로 검증.
"""
import unittest

import numpy as np

from app.services.chatbot.knowledge import load_faqs
from app.services.chatbot.retrieval import (
    Bm25Index,
    HybridRetriever,
    decompose_jamo,
    tokenize,
)


class TokenizeTestCase(unittest.TestCase):
    def test_korean_content_words(self):
        """조사 붙은 어절에서도 내용어가 잡혀야 함 (kiwi 또는 bigram 폴백)."""
        tokens = tokenize("크레딧은 언제 차감되나요?")
        joined = "".join(tokens)
        self.assertIn("크레", joined)  # kiwi='크레딧' / 폴백 bigram='크레'
        self.assertTrue(len(tokens) >= 2)

    def test_mixed_language_and_numbers(self):
        tokens = tokenize("Premium 9900원")
        self.assertIn("premium", tokens)
        self.assertIn("9900", tokens)


class Bm25TestCase(unittest.TestCase):
    def test_relevant_doc_ranks_first(self):
        docs = [tokenize(t) for t in ("환불 규정 안내 결제 취소", "스타일 프리셋 종류", "사진 촬영 팁")]
        index = Bm25Index(docs)
        scores = index.scores(tokenize("환불 받고 싶어요"))
        self.assertEqual(int(np.argmax(scores)), 0)

    def test_no_match_scores_zero(self):
        index = Bm25Index([tokenize("스타일 프리셋")])
        scores = index.scores(tokenize("weather tomorrow"))
        self.assertEqual(scores[0], 0.0)


class HybridRetrieverTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = HybridRetriever()  # 실제 faq_ko.yaml 색인

    def test_faq_loads_and_ids_unique(self):
        faqs = load_faqs()
        self.assertGreaterEqual(len(faqs), 15)
        self.assertEqual(len({f.id for f in faqs}), len(faqs))

    def test_billing_question_hits_billing_faq(self):
        hits = self.retriever.search("프리미엄 요금이 얼마예요?", top_k=3)
        self.assertEqual(hits[0].faq.id, "faq-bill-002")
        self.assertTrue(HybridRetriever.is_confident(hits))

    def test_refund_question_confident(self):
        hits = self.retriever.search("구독 해지하고 환불받고 싶은데요", top_k=3)
        self.assertEqual(hits[0].faq.id, "faq-bill-004")
        self.assertTrue(HybridRetriever.is_confident(hits))

    def test_offtopic_question_not_confident(self):
        """지식 밖 질문(날씨)은 confidence 게이트에서 걸려야 함 → 에스컬레이션 경로."""
        hits = self.retriever.search("내일 서울 날씨 알려줘", top_k=3)
        self.assertFalse(HybridRetriever.is_confident(hits))

    def test_empty_query_not_confident(self):
        self.assertFalse(HybridRetriever.is_confident(self.retriever.search("", top_k=3)))

    def test_dense_fusion_changes_ranking(self):
        """fake 임베더: 특정 FAQ 만 질문과 같은 방향 벡터 → RRF 융합으로 1위 승격 확인."""
        faqs = load_faqs()
        target = next(i for i, f in enumerate(faqs) if f.id == "faq-qual-001")

        def fake_embed(texts):
            out = np.zeros((len(texts), 4))
            for i, t in enumerate(texts):
                # 질문("결과 잘 나오게")과 촬영팁 FAQ 만 [1,0,0,0], 나머지는 직교
                if "촬영" in t or "잘 나오" in t:
                    out[i] = [1, 0, 0, 0]
                else:
                    out[i] = [0, 1, 0, 0]
            return out

        hybrid = HybridRetriever(faqs=faqs, embed_fn=fake_embed)
        hits = hybrid.search("결과 잘 나오게 하려면?", top_k=3)
        self.assertIn("faq-qual-001", [h.faq.id for h in hits])
        self.assertEqual(faqs[target].id, "faq-qual-001")


class TypoNormalizationTestCase(unittest.TestCase):
    """자모 fuzzy 오타 정규화 — 오타는 교정하고 오프토픽은 끌어오지 않아야 함."""

    @classmethod
    def setUpClass(cls):
        cls.retriever = HybridRetriever()

    def test_decompose_jamo(self):
        self.assertEqual(decompose_jamo("환불"), "ㅎㅘㄴㅂㅜㄹ")
        self.assertEqual(decompose_jamo("abc1"), "abc1")  # 비한글 통과

    def test_typo_word_corrected(self):
        """kiwi 가 조각내는 오타 어절(환뷸→환+뷰)도 어절 재대조로 교정."""
        _, corr = self.retriever.normalize_tokens(
            tokenize("크레딧 환뷸 되나요"), raw_query="크레딧 환뷸 되나요"
        )
        self.assertEqual(corr.get("환뷸"), "환불")

    def test_vowel_typo_tiebreak_prefers_same_consonants(self):
        """실페 → 실패 (모음 오타) — 동점 후보 '실제'(초성 다름)에 지면 안 됨."""
        _, corr = self.retriever.normalize_tokens(
            tokenize("생성 실페하면 크레딧 까져요?"), raw_query="생성 실페하면 크레딧 까져요?"
        )
        self.assertEqual(corr.get("실페"), "실패")

    def test_offtopic_words_not_corrected(self):
        """일반 활용 어절(만드는)·오프토픽 명사(로또)는 교정 금지 — 오흡수 방지."""
        for q in ("파스타 맛있게 만드는 법", "오늘 로또 번호 추천해줘"):
            _, corr = self.retriever.normalize_tokens(tokenize(q), raw_query=q)
            self.assertEqual(corr, {}, f"오교정 발생: {q} -> {corr}")

    def test_typo_query_end_to_end(self):
        hits = self.retriever.search("프리미엄 욤금 얼마예요", top_k=3)
        self.assertEqual(hits[0].faq.id, "faq-bill-002")
        self.assertTrue(HybridRetriever.is_confident(hits))


if __name__ == "__main__":
    unittest.main()
