"""고객센터 챗봇 (RAG) 패키지 — 담당: 한의정.

구성:
  knowledge.py    FAQ 단일 원본 로더 (faq_ko.yaml → FaqEntry)
  retrieval.py    하이브리드 검색 (BM25 직접구현 + dense 주입식, RRF 융합, confidence 게이트)
  chat_service.py 답변 생성 + 1:1 문의 에스컬레이션 (검색 실패 시 LLM 호출 0회)
  chat_graph.py   LangGraph 답변 품질 게이트 (제거 가능 — copy_graph 패턴)

HTTP 노출: app/api/chatbot.py (main.py 등록은 연정님 도메인 — 팀 조율 후).
"""
from .chat_service import ChatResult, ChatService, get_service  # noqa: F401
from .knowledge import FaqEntry, load_faqs  # noqa: F401
from .retrieval import HybridRetriever, RetrievalHit  # noqa: F401
