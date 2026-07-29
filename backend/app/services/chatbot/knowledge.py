"""고객센터 챗봇 지식 베이스 로더 — 담당: 한의정.

FAQ 단일 원본: services/chatbot/data/faq_ko.yaml
  - FAQ 게시판 초안과 챗봇 RAG 지식을 같은 파일에서 읽는다 (이원화 금지).
  - needs_confirmation=True 항목은 정책 미확정 → 챗봇 답변에 1:1 문의 안내를 덧붙인다.

DB 이관 시나리오: FAQ 테이블(범수님 도메인)이 생기면 load_faqs() 구현만 DB 조회로
교체하면 된다 — 상위(retrieval/chat_service)는 FaqEntry 리스트만 본다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

_DATA_PATH = Path(__file__).resolve().parent / "data" / "faq_ko.yaml"


@dataclass(frozen=True)
class FaqEntry:
    """FAQ 1건. 검색 대상 텍스트 = question + keywords + answer."""

    id: str
    category: str
    question: str
    answer: str
    keywords: tuple[str, ...] = field(default_factory=tuple)
    needs_confirmation: bool = False

    @property
    def search_text(self) -> str:
        """색인용 텍스트. 질문·동의어에 가중을 주기 위해 question 을 2회 반복."""
        return "\n".join([self.question, self.question, " ".join(self.keywords), self.answer])


@lru_cache(maxsize=1)
def load_faqs(path: str | None = None) -> tuple[FaqEntry, ...]:
    """FAQ YAML 로드 + 스키마 검증. 결과는 캐시 (파일 수정 시 프로세스 재시작 필요)."""
    raw = yaml.safe_load(Path(path or _DATA_PATH).read_text(encoding="utf-8"))
    entries: list[FaqEntry] = []
    seen: set[str] = set()
    for item in raw.get("faqs", []):
        faq_id = item["id"]
        if faq_id in seen:
            raise ValueError(f"FAQ id 중복: {faq_id}")
        seen.add(faq_id)
        entries.append(
            FaqEntry(
                id=faq_id,
                category=item["category"],
                question=item["question"].strip(),
                answer=item["answer"].strip(),
                keywords=tuple(str(k) for k in item.get("keywords", [])),  # YAML 이 9900 을 int 로 파싱
                needs_confirmation=bool(item.get("needs_confirmation", False)),
            )
        )
    if not entries:
        raise ValueError("FAQ 데이터가 비어있음")
    return tuple(entries)
