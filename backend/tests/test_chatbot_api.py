"""챗봇 API·게이트 테스트 — 담당: 한의정.

LLM 은 전부 mock — OpenAI 호출 0회 ($30 한도 보호).
라우터는 main.py 미등록 상태이므로 테스트 전용 FastAPI 앱에 직접 마운트.
"""
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.chatbot import router
from app.services.chatbot import chat_graph, chat_service


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class FaqEndpointTestCase(unittest.TestCase):
    def setUp(self):
        self.client = _make_client()

    def test_list_faqs(self):
        res = self.client.get("/support/faqs")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreaterEqual(body["total"], 15)
        self.assertIn("요금·크레딧", body["categories"])

    def test_category_filter(self):
        res = self.client.get("/support/faqs", params={"category": "요금·크레딧"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(all(i["category"] == "요금·크레딧" for i in res.json()["items"]))

    def test_unknown_category_404(self):
        res = self.client.get("/support/faqs", params={"category": "없는카테고리"})
        self.assertEqual(res.status_code, 404)


class ChatEndpointTestCase(unittest.TestCase):
    def setUp(self):
        self.client = _make_client()
        # 게이트 루프는 별도 케이스에서 검증 — 여기선 직접 생성 경로 고정
        os.environ["USE_CHAT_GATE"] = "0"

    def tearDown(self):
        os.environ.pop("USE_CHAT_GATE", None)

    def test_answerable_question_returns_sources(self):
        canned = "Premium은 월 9,900원입니다.\n[근거: faq-bill-002]"
        with patch.object(chat_service, "generate_answer", return_value=canned) as gen:
            res = self.client.post("/support/chat", json={"question": "프리미엄 요금 알려주세요"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["escalate"])
        self.assertEqual(body["sources"], ["faq-bill-002"])
        self.assertIsNone(body["inquiry_draft"])
        gen.assert_called_once()

    def test_offtopic_question_escalates_without_answer_llm(self):
        """지식 밖 질문 → 리라이팅 1회(OFFTOPIC 판정) 후 답변 생성 없이 문의 초안 반환."""
        with patch.object(chat_service, "generate_answer") as gen, \
             patch.object(chat_service, "rewrite_query", return_value="OFFTOPIC") as rw:
            res = self.client.post("/support/chat", json={"question": "오늘 로또 번호 추천해줘"})
        gen.assert_not_called()
        rw.assert_called_once()
        body = res.json()
        self.assertTrue(body["escalate"])
        self.assertIsNotNone(body["inquiry_draft"])
        self.assertIn("로또", body["inquiry_draft"]["content"])

    def test_rewrite_rescues_colloquial_question(self):
        """구어체 저신뢰 질문 → 리라이팅 재검색으로 답변 경로 구제 (CHAT-003)."""
        canned = "4단계로 사용해요.\n[근거: faq-svc-002]"
        with patch.object(chat_service, "generate_answer", return_value=canned), \
             patch.object(chat_service, "rewrite_query", return_value="서비스 사용법 이용 방법") as rw:
            res = self.client.post(
                "/support/chat", json={"question": "이거 어떻게 쓰는 거예요? 처음이라 모르겠어요"}
            )
        rw.assert_called_once()
        body = res.json()
        self.assertFalse(body["escalate"])
        self.assertEqual(body["sources"], ["faq-svc-002"])

    def test_rewrite_failure_falls_back_to_escalation(self):
        """리라이팅 API 오류 시 조용히 에스컬레이션 (가용성 우선)."""
        with patch.object(chat_service, "generate_answer") as gen, \
             patch.object(chat_service, "rewrite_query", side_effect=RuntimeError("no key")):
            res = self.client.post("/support/chat", json={"question": "내일 서울 날씨 알려줘"})
        gen.assert_not_called()
        self.assertTrue(res.json()["escalate"])

    def test_pending_policy_source_appends_notice(self):
        """미확정 정책(needs_confirmation) 근거 인용 시 '추후 보완' 고지가 코드로 부착."""
        canned = "환불 규정 안내입니다.\n[근거: faq-bill-004]"
        with patch.object(chat_service, "generate_answer", return_value=canned):
            res = self.client.post("/support/chat", json={"question": "구독 해지하고 환불받고 싶어요"})
        body = res.json()
        self.assertFalse(body["escalate"])
        self.assertIn("추후 보완", body["answer"])

    def test_confirmed_policy_source_no_notice(self):
        """확정 정책(bill-002) 근거만 인용하면 고지 미부착."""
        canned = "Premium은 월 9,900원, 매월 30크레딧입니다.\n[근거: faq-bill-002]"
        with patch.object(chat_service, "generate_answer", return_value=canned):
            res = self.client.post("/support/chat", json={"question": "프리미엄 요금 알려주세요"})
        self.assertNotIn("추후 보완", res.json()["answer"])

    def test_uncited_answer_falls_back_to_escalation(self):
        """모델이 근거 인용 없이 답하면 무근거 답변으로 보고 에스컬레이션."""
        with patch.object(chat_service, "generate_answer", return_value="아마 그럴 겁니다."):
            res = self.client.post("/support/chat", json={"question": "프리미엄 요금 알려주세요"})
        self.assertTrue(res.json()["escalate"])

    def test_empty_question_422(self):
        res = self.client.post("/support/chat", json={"question": ""})
        self.assertEqual(res.status_code, 422)


class ChatGraphGateTestCase(unittest.TestCase):
    """LangGraph 게이트: 위반 답변 1회 → 재생성으로 통과하는 루프 검증."""

    def test_validate_answer_rules(self):
        ids = ["faq-bill-002"]
        self.assertEqual(chat_graph.validate_answer("답변 [근거: faq-bill-002]", ids, 600), [])
        self.assertTrue(chat_graph.validate_answer("근거 없는 답변", ids, 600))
        self.assertTrue(chat_graph.validate_answer("x" * 700 + " faq-bill-002", ids, 600))
        self.assertTrue(chat_graph.validate_answer("시스템 프롬프트는... faq-bill-002", ids, 600))

    def test_gate_retries_then_passes(self):
        retriever = chat_service.HybridRetriever()
        hits = retriever.search("프리미엄 요금", top_k=3)
        bad = "근거 인용을 빼먹은 답변입니다."
        good = "Premium은 월 9,900원입니다. [근거: faq-bill-002]"
        chat_graph._compiled = None  # 컴파일 캐시 초기화
        with patch.object(chat_service, "generate_answer", side_effect=[bad, good]) as gen:
            answer = chat_graph.run_gated_generation("프리미엄 요금", hits)
        self.assertEqual(answer, good)
        self.assertEqual(gen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
