"""하이브리드 검색 (BM25 + dense 임베딩, RRF 융합) — 담당: 한의정.

설계 결정:
  - BM25 는 외부 라이브러리 없이 직접 구현 (Okapi BM25, k1=1.5 b=0.75).
    코퍼스가 FAQ 수십 건이라 색인·검색 모두 ms 단위 — 의존성 추가보다 투명성 우선.
  - 한국어 토큰화는 kiwipiepy(형태소) 우선, 미설치 시 정규식+문자 bigram 폴백.
    폴백도 한국어 매칭이 되는 이유: 문자 bigram 이 조사 붙은 어절("크레딧은"→"크레","레딧","딧은")
    사이의 부분 일치를 잡아준다.
  - dense 는 embed_fn 주입식 (Callable[[list[str]], np.ndarray]) — 로컬(KURE-v1 등
    transformers 로드)·OpenAI 임베딩·테스트용 fake 를 같은 인터페이스로 교체.
    embed_fn=None 이면 BM25 단독 동작 (로컬 Mac 기본값 — 모델 다운로드 없이 개발).
  - 융합은 RRF(Reciprocal Rank Fusion, k=60): 점수 스케일이 다른 두 랭킹을
    정규화 없이 안전하게 합치는 표준 기법.
  - confidence 게이트: 1위 문서의 BM25 원점수와 질문-토큰 겹침으로 "지식 밖 질문"을
    판정 → 챗봇이 환각 대신 1:1 문의 에스컬레이션을 택하게 한다.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np

from .knowledge import FaqEntry, load_faqs

logger = logging.getLogger(__name__)

# RRF 상수 (Cormack et al. 2009 권장값)
_RRF_K = 60
# confidence 게이트 임계값 — eval_chatbot_retrieval.py 골든셋으로 튜닝한 값.
# 절대 점수만으로는 부족 (실측: "로또 번호"가 "비밀번호"의 '번호'와 겹쳐 3.0 획득).
# → 질문 내용어 커버리지(겹친 토큰/전체 질문 토큰)를 함께 요구한다.
MIN_BM25_SCORE = 2.0     # 1위 문서 BM25 원점수 하한
MIN_COVERAGE = 0.5       # 질문 내용어 중 1위 문서와 겹친 비율 하한

EmbedFn = Callable[[Sequence[str]], np.ndarray]


# --- 한국어 토큰화 ------------------------------------------------------------
_HANGUL_WORD = re.compile(r"[가-힣]+|[a-zA-Z]+|[0-9]+")
# 폴백 토크나이저에서 걸러낼 1글자 조사·형식어 (bigram 이전 어절 단위 노이즈 컷)
_STOP_TOKENS = frozenset(
    {"은", "는", "이", "가", "을", "를", "에", "의", "도", "로", "와", "과", "요", "죠", "게"}
)


def _try_load_kiwi():  # noqa: ANN202
    """kiwipiepy 지연 로드. 미설치 환경(Docker 웹 백엔드 등)에서는 None → 폴백."""
    try:
        from kiwipiepy import Kiwi

        return Kiwi()
    except Exception:  # noqa: BLE001 — ImportError 외 모델 로드 실패도 폴백
        logger.info("kiwipiepy 미사용 — 정규식+bigram 폴백 토크나이저로 동작")
        return None


_KIWI = None
_KIWI_LOADED = False
# 내용어로 취급할 kiwi 품사: 일반/고유명사·동사/형용사·외국어·숫자·어근.
# NNB(의존명사: 것/수/번/개)는 전 문서에 깔린 노이즈라 제외 — 골든셋 실측으로 확인.
_KIWI_KEEP = ("NNG", "NNP", "VV", "VA", "SL", "SN", "XR")


def tokenize(text: str) -> list[str]:
    """검색용 내용어 토큰 추출. kiwi 형태소 우선, 폴백 = 어절 + 문자 bigram."""
    global _KIWI, _KIWI_LOADED  # noqa: PLW0603 — 프로세스 1회 지연 초기화
    if not _KIWI_LOADED:
        _KIWI = _try_load_kiwi()
        _KIWI_LOADED = True

    text = text.lower()
    if _KIWI is not None:
        # 1글자 동사·형용사 어간(하/주/되/보…)은 전 문서에 깔린 노이즈 — 명사류만 1글자 허용
        return [
            t.form
            for t in _KIWI.tokenize(text)
            if t.tag.startswith(_KIWI_KEEP)
            and (len(t.form) > 1 or not t.tag.startswith(("VV", "VA")))
        ]

    tokens: list[str] = []
    for word in _HANGUL_WORD.findall(text):
        if word in _STOP_TOKENS:
            continue
        tokens.append(word)
        # 한글 어절은 문자 bigram 추가 — 조사 변형("크레딧이/크레딧은") 간 부분 일치용
        if re.match(r"[가-힣]{3,}", word):
            tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
    return tokens


def noun_tokens(text: str) -> list[str]:
    """오타 교정 사전용 명사류(명사·외래어·숫자) 토큰만 추출.

    동사·형용사(만들/찍/알리)를 교정 후보에 넣으면 "만드는" 같은 정상 활용 어절까지
    교정되어 오프토픽 질문이 지식 안으로 끌려온다 (골든셋 실측) — 명사만 허용.
    kiwi 미설치 시 폴백: tokenize 결과 중 2글자+ (bigram 제외 불가하므로 근사).
    """
    global _KIWI, _KIWI_LOADED  # noqa: PLW0603
    if not _KIWI_LOADED:
        _KIWI = _try_load_kiwi()
        _KIWI_LOADED = True
    if _KIWI is None:
        return [t for t in tokenize(text) if len(t) >= 2]
    return [
        t.form
        for t in _KIWI.tokenize(text.lower())
        if t.tag.startswith(("NNG", "NNP", "SL", "SN")) and len(t.form) >= 2
    ]


# --- 오타 정규화 (자모 분해 + rapidfuzz) ----------------------------------------
# bidmate fuzzy_normalize_query(음절 단위, threshold 80)의 개선판.
# 한글 오타는 대부분 모음/받침 1개 차이라 음절 비교로는 유사도가 절반으로 꺼진다
# (환불↔환뷸 = 음절 50% vs 자모 83%). → 자모 분해 후 Levenshtein 유사도로 비교.
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
TYPO_MIN_SIMILARITY = 0.8  # 자모 유사도 하한 — 골든셋 실측 튜닝값 (오프토픽 오교정 방지)


def decompose_jamo(word: str) -> str:
    """한글 음절을 초·중·종성 자모열로 분해 (비한글 문자는 그대로 통과)."""
    out: list[str] = []
    for ch in word:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            idx = code - 0xAC00
            out.append(_CHO[idx // 588])
            out.append(_JUNG[(idx % 588) // 28])
            if idx % 28:
                out.append(_JONG[idx % 28])
        else:
            out.append(ch)
    return "".join(out)


def _try_load_levenshtein():  # noqa: ANN202
    """rapidfuzz 지연 로드. 미설치 시 오타 정규화만 비활성 (검색 자체는 동작)."""
    try:
        from rapidfuzz.distance import Levenshtein

        return Levenshtein
    except ImportError:
        logger.info("rapidfuzz 미설치 — 오타 정규화 비활성")
        return None


_LEV = None
_LEV_LOADED = False


# --- BM25 (Okapi) -------------------------------------------------------------
class Bm25Index:
    """소규모 코퍼스용 in-memory BM25. 문서 = FAQ 1건의 search_text."""

    def __init__(self, docs: Sequence[Sequence[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.doc_tokens = [Counter(d) for d in docs]
        self.doc_lens = [sum(c.values()) for c in self.doc_tokens]
        self.avg_len = (sum(self.doc_lens) / len(self.doc_lens)) if docs else 0.0
        df: Counter[str] = Counter()
        for c in self.doc_tokens:
            df.update(c.keys())
        n = len(docs)
        # BM25+ 스타일의 하한 없는 표준 idf. 코퍼스가 작아 음수 idf 방지에 +1 스무딩
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query_tokens: Sequence[str]) -> np.ndarray:
        out = np.zeros(len(self.doc_tokens), dtype=np.float64)
        for i, (counts, dlen) in enumerate(zip(self.doc_tokens, self.doc_lens)):
            denom_norm = self.k1 * (1 - self.b + self.b * dlen / (self.avg_len or 1.0))
            s = 0.0
            for t in query_tokens:
                tf = counts.get(t)
                if not tf:
                    continue
                s += self.idf.get(t, 0.0) * tf * (self.k1 + 1) / (tf + denom_norm)
            out[i] = s
        return out


# --- 하이브리드 리트리버 -------------------------------------------------------
@dataclass(frozen=True)
class RetrievalHit:
    faq: FaqEntry
    score: float          # RRF 융합 점수 (랭킹용)
    bm25_score: float     # BM25 원점수 (confidence 게이트용)
    token_overlap: int    # 질문·문서 겹친 내용어 수
    query_coverage: float  # 겹친 내용어 / 질문 전체 내용어 (0~1)


class HybridRetriever:
    """BM25(+선택적 dense) 하이브리드 검색기.

    embed_fn 이 없으면 BM25 단독 — 로컬 개발 기본값.
    embed_fn 이 있으면 색인 시 FAQ 임베딩을 미리 계산해 두고 코사인 유사도 랭킹을
    BM25 랭킹과 RRF 로 융합한다.
    """

    def __init__(self, faqs: Optional[Sequence[FaqEntry]] = None, embed_fn: Optional[EmbedFn] = None) -> None:
        self.faqs = tuple(faqs) if faqs is not None else load_faqs()
        self._doc_token_sets: list[set[str]] = []
        docs = []
        for f in self.faqs:
            toks = tokenize(f.search_text)
            docs.append(toks)
            self._doc_token_sets.append(set(toks))
        self.bm25 = Bm25Index(docs)
        # 오타 정규화용 어휘 사전: 색인 문서의 "명사류" 토큰만 (동사 교정 = 오프토픽 오흡수)
        self._vocab_jamo = {
            t: decompose_jamo(t) for f in self.faqs for t in noun_tokens(f.search_text)
        }
        self.embed_fn = embed_fn
        self._doc_emb: Optional[np.ndarray] = None
        if embed_fn is not None:
            emb = np.asarray(embed_fn([f.search_text for f in self.faqs]), dtype=np.float64)
            self._doc_emb = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)

    @staticmethod
    def _rrf(rank: int) -> float:
        return 1.0 / (_RRF_K + rank + 1)

    def _best_vocab_match(self, word: str, prefix: bool) -> tuple[Optional[str], float]:
        """word 와 가장 가까운 어휘 토큰. prefix=True 면 어절(조사 붙음) 대응으로
        vocab 길이 창(prefix window)과도 비교한다.

        동점 타이브레이크 = 초성열 일치 우선. 한글 오타는 모음·받침(ㅐ↔ㅔ 등)이
        압도적이라, 초성이 같은 후보가 정답일 확률이 높다 (실측: 실페 → 실패 vs 실제).
        """
        word_jamo = decompose_jamo(word)
        word_cho = "".join(ch for ch in word_jamo if ch in _CHO)
        best: tuple[float, int, Optional[str]] = (0.0, 0, None)
        for vocab_tok, vocab_jamo in self._vocab_jamo.items():
            sim = _LEV.normalized_similarity(word_jamo, vocab_jamo)
            if prefix and len(word_jamo) > len(vocab_jamo):
                # 어절 앞부분만 vocab 과 비교 (뒤는 조사/어미) — 창 크기 ±1 로 이탈 흡수
                for w in (len(vocab_jamo) - 1, len(vocab_jamo), len(vocab_jamo) + 1):
                    if 0 < w <= len(word_jamo):
                        sim = max(sim, _LEV.normalized_similarity(word_jamo[:w], vocab_jamo))
            if sim >= TYPO_MIN_SIMILARITY:
                vocab_cho = "".join(ch for ch in vocab_jamo if ch in _CHO)
                cho_match = 1 if word_cho.startswith(vocab_cho) or vocab_cho.startswith(word_cho) else 0
                cand = (sim, cho_match, vocab_tok)
                if (cand[0], cand[1]) > (best[0], best[1]):
                    best = cand
        return best[2], best[0]

    def normalize_tokens(self, tokens: Sequence[str], raw_query: str = "") -> tuple[list[str], dict[str, str]]:
        """오타 교정 2단계. (교정 반영 토큰열, 교정 맵) 반환.

        1단계 (토큰): 사전에 없는 2글자+ 토큰을 자모 fuzzy 로 치환 (채험→체험).
        2단계 (어절): kiwi 가 오타 어절을 조각낸 경우(환뷸→환+뷰) 원형을 못 보므로,
          공백 단위 어절을 prefix 창으로 재대조해 교정 토큰을 "추가"한다 — 기존 토큰을
          지우지 않으므로 (append-only) 교정 실패가 검색을 더 나쁘게 만들지 않는다.

        보수 규칙 — 오프토픽을 지식 안으로 끌어오지 않기 위해 유사도 하한
        TYPO_MIN_SIMILARITY 적용 (실측: 환불↔환뷸 0.83 / 로또↔로딩 0.40).
        """
        global _LEV, _LEV_LOADED  # noqa: PLW0603 — 프로세스 1회 지연 초기화
        if not _LEV_LOADED:
            _LEV = _try_load_levenshtein()
            _LEV_LOADED = True
        if _LEV is None or not self._vocab_jamo:
            return list(tokens), {}

        corrected: list[str] = []
        corrections: dict[str, str] = {}
        for tok in tokens:
            if len(tok) < 2 or tok in self._vocab_jamo:
                corrected.append(tok)
                continue
            match, _sim = self._best_vocab_match(tok, prefix=False)
            if match is not None:
                corrections[tok] = match
                corrected.append(match)
            else:
                corrected.append(tok)

        known = set(corrected)
        for word in _HANGUL_WORD.findall(raw_query.lower()):
            if len(word) < 2 or word in self._vocab_jamo:
                continue
            # 어절 안에 이미 "사전 어휘" 토큰이 잡혀 있으면(회원가임의 '회원') 건너뜀.
            # 사전에 없는 조각(로그은이의 '로그')은 재대조 대상 — 어휘 기준으로만 판단.
            if any(t in word for t in known if len(t) >= 2 and t in self._vocab_jamo):
                continue
            match, _sim = self._best_vocab_match(word, prefix=True)
            if match is not None and match not in known:
                # kiwi 가 오타 어절을 쪼갠 조각(환뷸→환+뷰)은 커버리지 분모만 오염 → 제거
                fragments = {t for t in tokenize(word) if t not in self._vocab_jamo}
                corrected = [t for t in corrected if t not in fragments]
                corrections[word] = match
                corrected.append(match)
                known.add(match)
        if corrections:
            logger.info("오타 정규화: %s", corrections)
        return corrected, corrections

    def search(self, query: str, top_k: int = 3) -> list[RetrievalHit]:
        q_tokens, _ = self.normalize_tokens(tokenize(query), raw_query=query)
        bm25_scores = self.bm25.scores(q_tokens)
        bm25_rank = np.argsort(-bm25_scores)

        fused = {int(i): self._rrf(r) for r, i in enumerate(bm25_rank)}
        if self._doc_emb is not None and self.embed_fn is not None:
            q_emb = np.asarray(self.embed_fn([query]), dtype=np.float64)[0]
            q_emb = q_emb / (np.linalg.norm(q_emb) + 1e-9)
            dense_rank = np.argsort(-(self._doc_emb @ q_emb))
            for r, i in enumerate(dense_rank):
                fused[int(i)] = fused.get(int(i), 0.0) + self._rrf(r)

        q_set = set(q_tokens)
        order = sorted(fused, key=lambda i: -fused[i])[:top_k]
        return [
            RetrievalHit(
                faq=self.faqs[i],
                score=fused[i],
                bm25_score=float(bm25_scores[i]),
                token_overlap=len(q_set & self._doc_token_sets[i]),
                query_coverage=(len(q_set & self._doc_token_sets[i]) / len(q_set)) if q_set else 0.0,
            )
            for i in order
        ]

    @staticmethod
    def is_confident(hits: Sequence[RetrievalHit]) -> bool:
        """검색 결과로 답해도 되는가. False = 지식 밖 질문 → 에스컬레이션."""
        if not hits:
            return False
        top = hits[0]
        return top.bm25_score >= MIN_BM25_SCORE and top.query_coverage >= MIN_COVERAGE


# --- dense 임베딩 백엔드 (옵션) -------------------------------------------------
def build_transformers_embedder(model_name: str = "nlpai-lab/KURE-v1") -> EmbedFn:
    """KURE-v1(한국어 특화, bge-m3 계열) 임베딩 로더 — VM/서버 전용.

    로컬 Mac 기본 개발 흐름에서는 호출하지 않는다 (모델 ~2GB 다운로드).
    sentence-transformers 없이 transformers 만으로 mean pooling 구현.
    """
    import torch  # noqa: PLC0415 — 지연 임포트 (CPU 환경 기동시간 보호)
    from transformers import AutoModel, AutoTokenizer  # noqa: PLC0415

    tok = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    def _embed(texts: Sequence[str]) -> np.ndarray:
        with torch.no_grad():
            enc = tok(list(texts), padding=True, truncation=True, max_length=512, return_tensors="pt")
            out = model(**enc).last_hidden_state
            mask = enc["attention_mask"].unsqueeze(-1)
            pooled = (out * mask).sum(1) / mask.sum(1).clamp(min=1)
        return pooled.cpu().numpy()

    return _embed
