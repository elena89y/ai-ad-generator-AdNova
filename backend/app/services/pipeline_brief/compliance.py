"""규정 컴플라이언스 게이트 — pipeline_brief(무-상품 경로) 전용. 담당: 한의정.

배경: 기능 1(텍스트 브리프 → 광고)의 결과물은 '예쁜 이미지'가 아니라 '정확한 정보 전달
레이아웃'이 본질이다. 일시·장소·문의처가 load-bearing 이고, 확산모델은 한글을 gibberish 로
렌더한다(함정 #3). 현수막으로 대량 배포된 날짜 오타는 회수 불가한 비가역 허위정보가 된다.

그래서 이 게이트는 AdNova 정직성 포지션의 연속이다 — 상품 세계의 '없던 가니시 금지'가
무-상품 세계에서는 '정보 정확성 보증 + 과장·허위 표현 차단'으로 치환된다.

역할분리(정직성 경계):
  - 정보 무결성(enforce_info_integrity): 유저 원문 발췌만 통과. 모델 재작성·창작 절대 금지.
    → 코드(PIL)가 이 원문을 그대로 조판(오탈자 0). 이건 구조적 하드 게이트.
  - 과장·허위 표현(check_copy): 표시광고법 일반 소지 표현 플래그. ⚠️ '보조 체크리스트'로
    포지셔닝 — 최종 책임은 유저(오탐 법적리스크 회피 위해 자동 삭제가 아니라 경고).

업종 확장: _REGISTRY 에 엔트리 추가로 의료(심의필)·학원(등록번호)·부동산(표시광고법)까지
같은 인터페이스로 확장한다. 현재 시드 = 범용 행사·이벤트(event).
"""
from __future__ import annotations

from dataclasses import dataclass

# copy_graph 의 상수를 여기 복제한다. copy_graph 도 '제거 가능 모듈'(파일 하나 삭제로 원복)이라,
# 최상위 import 로 묶으면 두 모듈의 탈부착 계약이 사슬로 엮이고 private 심볼에 결합된다.
# 두 값은 광고 규칙(길이·금칙어)이라 자주 안 변함 — 변경 시 copy_graph 와 함께 동기화.
_HEADLINE_MAX = 40   # == copy_graph.HEADLINE_MAX
_COPY_BANNED = ("최고", "1위", "100%", "무조건")  # == copy_graph._BANNED


@dataclass(frozen=True)
class VerticalRule:
    """업종별 규정 룰. 확장 시 여기 엔트리만 추가한다."""
    key: str
    label: str
    extra_banned: tuple[str, ...] = ()   # 업종 특화 과장·허위 소지 표현
    disclaimer: str = ""                  # 하단 고정 안내문(법정 문구 등). 없으면 빈 문자열


@dataclass(frozen=True)
class GateResult:
    """게이트 결과. violations 는 차단이 아니라 '보조 체크리스트'(면책 설계)."""
    ok: bool
    violations: tuple[str, ...] = ()
    info_lines: tuple[str, ...] = ()      # 무결성 강제 후(원문 발췌만)
    fine_print: str = ""


# --- 업종 레지스트리 -----------------------------------------------------------
# 행사·이벤트: 법정 고정문구는 없고, 과장·허위(표시광고법 일반)만 플래그.
_EVENT = VerticalRule(
    key="event",
    label="행사·이벤트",
    extra_banned=("국내 최초", "세계 최초", "유일", "완벽", "보장", "무제한", "평생"),
)

_REGISTRY: dict[str, VerticalRule] = {
    "event": _EVENT,
    # 후속 확장 예시(미구현 — 엔트리 추가만으로 붙는다):
    #   "medical": VerticalRule("medical", "병원·의원",
    #       extra_banned=("완치", "부작용 없는", "최고의 명의"),
    #       disclaimer="※ 본 광고는 의료광고 사전심의 대상입니다(심의필 번호 표기)."),
    #   "academy": VerticalRule("academy", "학원·교육",
    #       extra_banned=("합격 보장", "1등"),
    #       disclaimer="※ 학원 등록번호·교습비를 표기하세요."),
}

# 채도 낮춤(옥외광고물 저채도 기조) 힌트 상한 — 배경 생성 팔레트에 참고.
LOW_CHROMA_HINT = "muted, low-saturation, calm tones (fits Korean outdoor-signage norms)"


def get_rule(vertical: str) -> VerticalRule:
    """미정의 업종은 event(가장 관대)로 폴백 — 빈 화면보다 낫다."""
    return _REGISTRY.get((vertical or "event").lower(), _EVENT)


def enforce_info_integrity(info_lines) -> tuple[str, ...]:  # noqa: ANN001
    """정보줄 무결성 강제: 원문 그대로(strip·빈 줄 제거·순서 유지)만 통과.

    ⚠️ 여기서 절대 재작성·번역·정규화하지 않는다 — 일시/장소/문의처는 유저가 준 원문이
    곧 정본이다. 모델이 손대지 못하게 코드가 원문을 보존해 PIL 이 그대로 조판한다.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in (info_lines or ()):
        line = str(raw).strip()
        if line and line not in seen:
            out.append(line)
            seen.add(line)
    return tuple(out)


def check_copy(headline: str, subcopy: str, rule: VerticalRule) -> list[str]:
    """카피의 과장·허위 소지 표현·길이 위반 목록(빈 리스트 = 통과). 순수 함수."""
    violations: list[str] = []
    joined = f"{headline or ''}\n{subcopy or ''}"
    banned = set(_COPY_BANNED) | set(rule.extra_banned)
    hits = sorted(w for w in banned if w in joined)
    if hits:
        violations.append(f"과장·허위 소지 표현: {', '.join(hits)} (표시광고법 확인 권장)")
    if not (headline or "").strip():
        violations.append("헤드라인이 비어있음")
    elif len(headline.strip()) > _HEADLINE_MAX:
        violations.append(f"헤드라인이 너무 김({len(headline.strip())}자, {_HEADLINE_MAX}자 이내 권장)")
    return violations


def gate(headline: str, subcopy: str, info_lines, vertical: str = "event") -> GateResult:  # noqa: ANN001
    """무-상품 카피/정보 규정 게이트. 정보 무결성은 하드 강제, 과장표현은 보조 경고.

    반환의 violations 는 렌더를 막지 않는다(호출부가 로깅·표시). 유저가 최종 판단하도록 둔다.
    """
    rule = get_rule(vertical)
    info = enforce_info_integrity(info_lines)
    violations = tuple(check_copy(headline, subcopy, rule))
    return GateResult(
        ok=not violations,
        violations=violations,
        info_lines=info,
        fine_print=rule.disclaimer,
    )
