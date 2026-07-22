"""챗봇 API·게이트 테스트 — 담당: 한의정.

LLM 은 전부 mock — OpenAI 호출 0회 ($30 한도 보호).
라우터는 main.py 미등록 상태이므로 테스트 전용 FastAPI 앱에 직접 마운트.
"""
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.chatbot import router
from app.database.connection import Base, get_db
from app.services.chatbot import chat_graph, chat_service


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    # /support/chat 이 이벤트 로깅용 db 를 쓰므로 인메모리 DB 로 오버라이드 (StaticPool=단일 커넥션 공유)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine)

    def _override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    client._engine = engine  # 참조 유지 (GC 방지)
    return client


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
        # 게이트 루프·tier-2 는 별도 케이스에서 검증 — 여기선 근거 답변/에스컬레이션 이분법 고정
        os.environ["USE_CHAT_GATE"] = "0"
        os.environ["USE_GENERAL_TIER"] = "0"

    def tearDown(self):
        os.environ.pop("USE_CHAT_GATE", None)
        os.environ.pop("USE_GENERAL_TIER", None)

    def test_answerable_question_returns_sources(self):
        canned = "Premium은 월 9,900원입니다.\n[근거: faq-bill-002]"
        with patch.object(chat_service, "generate_answer", return_value=canned) as gen:
            res = self.client.post("/support/chat", json={"question": "프리미엄 요금 알려주세요"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["escalate"])
        self.assertEqual(body["sources"], ["faq-bill-002"])
        # 근거 태그는 내부 장치 — 사용자 표시 답변에선 제거 (연정님 피드백 07-21)
        self.assertNotIn("[근거", body["answer"])
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


class ChatGeneralTierTestCase(unittest.TestCase):
    """tier-2 일반답변: 안전 카테고리는 답하고, 요금·정책·오프토픽은 에스컬레이션."""

    def setUp(self):
        self.client = _make_client()
        os.environ["USE_GENERAL_TIER"] = "1"
        # 저신뢰 유도: 리라이팅은 지식 밖 키워드 반환(재검색도 실패), 근거 답변 경로 미진입
        self._rw = patch.object(chat_service, "rewrite_query", return_value="동영상 광고 편집")
        self._rw.start()

    def tearDown(self):
        self._rw.stop()
        os.environ.pop("USE_GENERAL_TIER", None)

    def test_general_tier_answers_safe_question(self):
        """FAQ 밖 안전 질문 → 일반답변(escalate=False, general=True, 헤지 포함)."""
        with patch.object(chat_service, "general_answer", return_value="일반적으로 가능합니다.") as g:
            res = self.client.post("/support/chat", json={"question": "동영상 광고도 편집되나요?"})
        g.assert_called_once()
        body = res.json()
        self.assertFalse(body["escalate"])
        self.assertIn("일반적으로", body["answer"])

    def test_general_tier_refuses_and_escalates(self):
        """FAQ 밖 질문이라도 general_answer 가 None(민감/오프토픽 판정) → 에스컬레이션."""
        # 저신뢰 질문(동영상 편집=KB 밖)으로 tier-2 진입 후, 모델이 거절했다고 가정
        with patch.object(chat_service, "general_answer", return_value=None) as g:
            res = self.client.post("/support/chat", json={"question": "동영상 광고도 편집되나요?"})
        g.assert_called_once()
        self.assertTrue(res.json()["escalate"])

    def test_offtopic_skips_general_tier(self):
        """리라이터 OFFTOPIC 판정이면 일반답변 시도 없이 바로 에스컬레이션."""
        self._rw.stop()
        with patch.object(chat_service, "rewrite_query", return_value="OFFTOPIC"), \
             patch.object(chat_service, "general_answer") as g:
            res = self.client.post("/support/chat", json={"question": "파스타 레시피 알려줘"})
        g.assert_not_called()
        self.assertTrue(res.json()["escalate"])
        self._rw.start()  # tearDown 대칭

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
