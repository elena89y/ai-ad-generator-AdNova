"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch, readApiError, readJsonSafely } from "@/lib/api";
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

const CATEGORY_LABELS: Record<string, string> = {
  general: "일반 문의",
  account: "계정 문의",
  billing: "결제 문의",
  generation: "광고 생성 문의",
  other: "기타",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "접수됨",
  in_progress: "처리 중",
  answered: "답변 완료",
  closed: "종료",
};

interface InquiryItem {
  id: number;
  category: string;
  title: string;
  content: string;
  status: string;
  answer?: string | null;
  created_at: string;
  answered_at?: string | null;
}

function formatInquiryDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).format(date);
}

export default function SupportPage() {
  const { toast, token } = useStudio();
  const [query, setQuery] = useState("");
  const [openStates, setOpenStates] = useState(FAQS.map((f) => f.open));
  const [formOpen, setFormOpen] = useState(false);
  const [category, setCategory] = useState("general");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loadingInquiries, setLoadingInquiries] = useState(false);
  const [inquiries, setInquiries] = useState<InquiryItem[]>([]);
  const [openInquiryId, setOpenInquiryId] = useState<number | null>(null);

  useEffect(() => {
    if (!token) {
      setInquiries([]);
      return;
    }

    let cancelled = false;
    setLoadingInquiries(true);

    async function loadInquiries() {
      try {
        const res = await apiFetch("/api/inquiries?limit=50");
        const data = await readJsonSafely(res);
        if (!res.ok) {
          throw new Error(readApiError(data, "문의 내역을 불러오지 못했습니다"));
        }
        const items = (data as { items?: InquiryItem[] } | null)?.items || [];
        if (!cancelled) setInquiries(items);
      } catch (err) {
        if (!cancelled) {
          setInquiries([]);
          toast(err instanceof Error ? err.message : "문의 내역을 불러오지 못했습니다");
        }
      } finally {
        if (!cancelled) setLoadingInquiries(false);
      }
    }

    void loadInquiries();
    return () => {
      cancelled = true;
    };
  }, [token, toast]);

  const q = query.trim().toLowerCase();
  const visible = FAQS.map((f) => !q || (f.q + f.a).toLowerCase().includes(q));
  const anyVisible = visible.some(Boolean);

  async function submitInquiry(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      toast("로그인 후 문의를 등록해 주세요");
      return;
    }
    if (!title.trim() || !content.trim()) {
      toast("문의 제목과 내용을 입력해 주세요");
      return;
    }

    setSubmitting(true);
    try {
      const res = await apiFetch("/api/inquiries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          title: title.trim(),
          content: content.trim(),
        }),
      });
      const data = await readJsonSafely(res);
      if (!res.ok) {
        throw new Error(readApiError(data, "문의 등록에 실패했습니다"));
      }
      const created = data as InquiryItem;
      setInquiries((current) => [created, ...current]);
      setTitle("");
      setContent("");
      setCategory("general");
      setFormOpen(false);
      setOpenInquiryId(created.id);
      toast("문의가 등록되었습니다");
    } catch (err) {
      toast(err instanceof Error ? err.message : "문의 등록에 실패했습니다");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <SubBar backHref="/studio" backLabel="대시보드" />
      <div className="page" style={{ maxWidth: 760 }}>
        <div style={{ textAlign: "center", margin: "10px 0 24px" }}>
          <h2 style={{ fontSize: 24, fontWeight: 800, letterSpacing: "-.5px", marginBottom: 6 }}>
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
              onClick={() => setOpenStates((prev) => prev.map((v, j) => (j === i ? !v : v)))}
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
          <div style={{ textAlign: "center", padding: 24, color: "var(--ink-mute)", fontSize: 13 }}>
            검색 결과가 없습니다.
          </div>
        )}

        <div
          style={{
            marginTop: 20,
            background: "linear-gradient(135deg,rgba(242,169,59,.1),rgba(196,46,92,.1))",
            border: "1px solid var(--line)",
            borderRadius: 14,
            padding: 18,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 3 }}>
                원하는 답을 못 찾으셨나요?
              </div>
              <div style={{ fontSize: 12.5, color: "var(--ink-soft)" }}>
                문의를 남기면 관리자가 확인 후 답변해 드려요.
              </div>
            </div>
            <button
              type="button"
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
              onClick={() => setFormOpen((open) => !open)}
            >
              {formOpen ? "문의 작성 닫기" : "문의하기"}
            </button>
          </div>

          {formOpen && (
            <form onSubmit={submitInquiry} style={{ display: "grid", gap: 10, marginTop: 16 }}>
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                style={{
                  height: 42,
                  border: "1px solid var(--line)",
                  borderRadius: 9,
                  background: "#26242D",
                  color: "var(--ink)",
                  padding: "0 11px",
                }}
              >
                {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <input
                value={title}
                maxLength={255}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="문의 제목을 입력하세요"
                style={{
                  height: 42,
                  border: "1px solid var(--line)",
                  borderRadius: 9,
                  background: "#26242D",
                  color: "var(--ink)",
                  padding: "0 11px",
                }}
              />
              <textarea
                value={content}
                maxLength={5000}
                onChange={(event) => setContent(event.target.value)}
                placeholder="문의 내용을 자세히 적어 주세요"
                style={{
                  minHeight: 120,
                  resize: "vertical",
                  border: "1px solid var(--line)",
                  borderRadius: 9,
                  background: "#26242D",
                  color: "var(--ink)",
                  padding: 11,
                  lineHeight: 1.55,
                }}
              />
              <button
                type="submit"
                disabled={submitting}
                style={{
                  justifySelf: "end",
                  padding: "10px 15px",
                  border: "none",
                  borderRadius: 9,
                  background: "var(--gold)",
                  color: "#16151A",
                  fontSize: 12.5,
                  fontWeight: 800,
                  cursor: submitting ? "wait" : "pointer",
                  opacity: submitting ? 0.65 : 1,
                }}
              >
                {submitting ? "등록 중..." : "문의 등록"}
              </button>
            </form>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", margin: "28px 0 10px" }}>
          <div style={{ fontSize: 14, fontWeight: 800 }}>내 문의</div>
          <span style={{ marginLeft: 8, color: "var(--ink-mute)", fontSize: 12 }}>
            {inquiries.length}건
          </span>
        </div>

        {!token ? (
          <div style={{ padding: 18, border: "1px solid var(--line)", borderRadius: 12, color: "var(--ink-mute)", fontSize: 13 }}>
            로그인 후 내 문의 내역을 확인할 수 있어요.
          </div>
        ) : loadingInquiries ? (
          <div style={{ padding: 18, color: "var(--ink-mute)", fontSize: 13 }}>문의 내역을 불러오는 중입니다.</div>
        ) : inquiries.length === 0 ? (
          <div style={{ padding: 18, border: "1px solid var(--line)", borderRadius: 12, color: "var(--ink-mute)", fontSize: 13 }}>
            등록한 문의가 없습니다.
          </div>
        ) : (
          <div style={{ display: "grid", gap: 9 }}>
            {inquiries.map((inquiry) => {
              const open = openInquiryId === inquiry.id;
              const hasAnswer = Boolean(inquiry.answer);
              return (
                <div key={inquiry.id} style={{ border: "1px solid var(--line)", borderRadius: 12, background: "var(--card)" }}>
                  <button
                    type="button"
                    onClick={() => setOpenInquiryId(open ? null : inquiry.id)}
                    style={{
                      display: "flex",
                      width: "100%",
                      alignItems: "center",
                      gap: 10,
                      border: 0,
                      background: "transparent",
                      color: "var(--ink)",
                      padding: "14px 16px",
                      textAlign: "left",
                      cursor: "pointer",
                    }}
                  >
                    <span
                      style={{
                        borderRadius: 99,
                        padding: "4px 8px",
                        background: hasAnswer ? "rgba(96,190,138,.14)" : "rgba(242,169,59,.14)",
                        color: hasAnswer ? "#78D6A0" : "var(--gold)",
                        fontSize: 11,
                        fontWeight: 700,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {STATUS_LABELS[inquiry.status] || inquiry.status}
                    </span>
                    <span style={{ flex: 1, fontSize: 13.5, fontWeight: 650 }}>{inquiry.title}</span>
                    <span style={{ color: "var(--ink-mute)", fontSize: 11.5, whiteSpace: "nowrap" }}>
                      {formatInquiryDate(inquiry.created_at)}
                    </span>
                  </button>
                  {open && (
                    <div style={{ borderTop: "1px solid var(--line)", padding: "14px 16px", fontSize: 12.5, lineHeight: 1.65 }}>
                      <div style={{ color: "var(--ink-mute)", marginBottom: 5 }}>
                        {CATEGORY_LABELS[inquiry.category] || inquiry.category}
                      </div>
                      <p style={{ margin: 0, whiteSpace: "pre-wrap", color: "var(--ink-soft)" }}>{inquiry.content}</p>
                      {hasAnswer && (
                        <div style={{ marginTop: 14, borderRadius: 9, background: "rgba(96,190,138,.08)", padding: 12 }}>
                          <div style={{ color: "#78D6A0", fontSize: 11.5, fontWeight: 800, marginBottom: 5 }}>
                            관리자 답변
                          </div>
                          <div style={{ whiteSpace: "pre-wrap" }}>{inquiry.answer}</div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
