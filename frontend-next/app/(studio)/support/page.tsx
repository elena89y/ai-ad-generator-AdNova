"use client";

import { useState } from "react";
import { useStudio } from "@/components/studio/StudioProvider";
import { SubBar } from "@/components/studio/chrome";

const FAQS = [
  {
    q: "크레딧은 어떻게 충전하나요?",
    a: "프리미엄 플랜에 가입하면 매월 30크레딧이 지급돼요. 부족하면 10크레딧당 4,900원에 추가 구매할 수 있어요.",
    open: false,
  },
  {
    q: "다운로드가 안 돼요.",
    a: "원본 다운로드는 프리미엄 플랜에서만 제공돼요. 무료 체험에서는 워터마크 미리보기와 사이트 이력 저장까지 가능합니다.",
    open: true,
  },
  {
    q: "생성한 광고는 어디에 저장되나요?",
    a: "모든 생성 결과는 '내 광고' 이력에 자동 저장돼요. 언제든 다시 보고 공유할 수 있어요.",
    open: false,
  },
  {
    q: "상품 사진은 어떻게 찍으면 좋나요?",
    a: "제품이 화면 중앙에 크게, 밝은 곳에서 단색 배경으로 찍으면 배경 제거와 합성 품질이 좋아져요.",
    open: false,
  },
];

export default function SupportPage() {
  const { toast } = useStudio();
  const [query, setQuery] = useState("");
  const [openStates, setOpenStates] = useState(FAQS.map((f) => f.open));

  const q = query.trim().toLowerCase();
  const visible = FAQS.map(
    (f) => !q || (f.q + f.a).toLowerCase().includes(q)
  );
  const anyVisible = visible.some(Boolean);

  return (
    <section>
      <SubBar backHref="/studio" backLabel="대시보드" />
      <div className="page" style={{ maxWidth: 760 }}>
        <div style={{ textAlign: "center", margin: "10px 0 24px" }}>
          <h2
            style={{
              fontSize: 24,
              fontWeight: 800,
              letterSpacing: "-.5px",
              marginBottom: 6,
            }}
          >
            무엇을 도와드릴까요?
          </h2>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 16 }}>
            자주 묻는 질문에서 먼저 찾아보세요.
          </p>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 9,
              maxWidth: 440,
              margin: "0 auto",
              padding: "12px 15px",
              background: "#26242D",
              border: "1px solid rgba(255,255,255,.1)",
              borderRadius: 12,
            }}
          >
            <span>🔍</span>
            <input
              type="search"
              placeholder="궁금한 점을 검색하세요"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              style={{
                flex: 1,
                border: 0,
                outline: 0,
                background: "transparent",
                color: "var(--ink)",
                fontSize: 13.5,
              }}
            />
          </div>
        </div>
        <div
          style={{
            fontSize: 12,
            fontWeight: 700,
            letterSpacing: ".06em",
            textTransform: "uppercase",
            color: "var(--ink-mute)",
            margin: "0 0 10px",
          }}
        >
          자주 묻는 질문
        </div>
        {FAQS.map((f, i) =>
          visible[i] ? (
            <div
              key={f.q}
              className={`faq${openStates[i] ? " open" : ""}`}
              onClick={() =>
                setOpenStates((prev) => prev.map((v, j) => (j === i ? !v : v)))
              }
            >
              <div className="q">
                {f.q}
                <span className="pm" />
              </div>
              <p className="a">{f.a}</p>
            </div>
          ) : null
        )}
        {!anyVisible && (
          <div
            style={{
              textAlign: "center",
              padding: 24,
              color: "var(--ink-mute)",
              fontSize: 13,
            }}
          >
            검색 결과가 없습니다.
          </div>
        )}
        <div
          style={{
            marginTop: 20,
            background:
              "linear-gradient(135deg,rgba(242,169,59,.1),rgba(196,46,92,.1))",
            border: "1px solid var(--line)",
            borderRadius: 14,
            padding: 18,
            display: "flex",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 3 }}>
              원하는 답을 못 찾으셨나요?
            </div>
            <div style={{ fontSize: 12.5, color: "var(--ink-soft)" }}>
              1:1 문의 기능은 준비 중이에요.
            </div>
          </div>
          <button
            style={{
              padding: "11px 18px",
              border: "none",
              borderRadius: 11,
              background: "var(--gold)",
              color: "#16151A",
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
            onClick={() => toast("1:1 문의 기능은 준비 중입니다")}
          >
            문의하기
          </button>
        </div>
      </div>
    </section>
  );
}
