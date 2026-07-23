"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { apiFetch, readApiError, readJsonSafely } from "@/lib/api";
import { useStudio } from "@/components/studio/StudioProvider";
import { SubBar } from "@/components/studio/chrome";
import { FAQ_CATEGORIES, FAQ_ITEMS } from "@/lib/faq-data";

/* FAQ 는 챗봇 지식 베이스(backend faq_ko.yaml → lib/faq-data.ts)와 단일 원본.
   기존 하드코딩 4문항은 KB 로 흡수됨(다운로드/충전은 정책 확정 전이라 비단정 문구).
   confirming=true 항목은 '추후 보완 필요' 배지 표시 (정책 확정 전 초안).
   챗봇(노바냥)의 근거 칩이 /support#faq-id 로 딥링크 — 해시로 자동 펼침. */

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

interface NoticePreview {
  id: number;
  title: string;
  published_at: string;
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

function formatNoticeDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
  }).format(date);
}

export default function SupportPage() {
  const { toast, token } = useStudio();
  const [query, setQuery] = useState("");
  const [openFaqId, setOpenFaqId] = useState<string | null>(null);
  const [catFilter, setCatFilter] = useState("전체");
  const [formOpen, setFormOpen] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);
  const [category, setCategory] = useState("general");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loadingInquiries, setLoadingInquiries] = useState(false);
  const [inquiries, setInquiries] = useState<InquiryItem[]>([]);
  const [openInquiryId, setOpenInquiryId] = useState<number | null>(null);
  const [recentNotices, setRecentNotices] = useState<NoticePreview[]>([]);

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

  useEffect(() => {
    let cancelled = false;

    async function loadRecentNotices() {
      try {
        const res = await apiFetch("/notices?limit=3");
        const data = (await readJsonSafely(res)) as { items?: NoticePreview[] } | null;
        if (res.ok && !cancelled) setRecentNotices(data?.items || []);
      } catch {
        if (!cancelled) setRecentNotices([]);
      }
    }

    void loadRecentNotices();
    return () => {
      cancelled = true;
    };
  }, []);

  // 챗봇 근거 칩 딥링크(#faq-id): 해당 항목 자동 펼침 + 스크롤
  useEffect(() => {
    const applyHash = () => {
      const id = window.location.hash.replace("#", "");
      if (id && FAQ_ITEMS.some((f) => f.id === id)) {
        setCatFilter("전체");
        setQuery("");
        setOpenFaqId(id);
        setTimeout(
          () => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" }),
          80
        );
      }
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
  }, []);

  // 챗봇 에스컬레이션 초안 프리필(?dcat&dtitle&dcontent) — useSearchParams 대신
  // window 파싱 (클라이언트 전용 페이지라 Suspense 경계 불필요)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const dtitle = params.get("dtitle");
    const dcontent = params.get("dcontent");
    if (!dtitle && !dcontent) return;
    const dcat = params.get("dcat");
    if (dcat && Object.hasOwn(CATEGORY_LABELS, dcat)) setCategory(dcat);
    if (dtitle) setTitle(dtitle);
    if (dcontent) setContent(dcontent);
    setFormOpen(true);
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 120);
  }, []);

  const q = query.trim().toLowerCase();
  const shownFaqs = FAQ_ITEMS.filter(
    (f) =>
      (catFilter === "전체" || f.category === catFilter) &&
      (!q || (f.question + f.answer).toLowerCase().includes(q))
  );
  const anyVisible = shownFaqs.length > 0;

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
      <SubBar />
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

        <section
          style={{
            margin: "0 0 26px",
            border: "1px solid var(--line)",
            borderRadius: 14,
            overflow: "hidden",
            background: "#211F27",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              padding: "15px 16px",
              borderBottom: recentNotices.length ? "1px solid var(--line)" : 0,
            }}
          >
            <div>
              <div style={{ fontSize: 14, fontWeight: 800 }}>공지사항</div>
              <div style={{ marginTop: 3, color: "var(--ink-mute)", fontSize: 12 }}>
                서비스 운영 소식과 중요한 안내를 확인하세요.
              </div>
            </div>
            <Link href="/notices" style={{ color: "var(--gold)", textDecoration: "none", fontSize: 12, fontWeight: 800, whiteSpace: "nowrap" }}>
              전체 보기 →
            </Link>
          </div>
          {recentNotices.length === 0 ? (
            <div style={{ padding: "15px 16px", color: "var(--ink-mute)", fontSize: 12.5 }}>
              새로운 공지사항이 없습니다.
            </div>
          ) : (
            recentNotices.map((notice) => (
              <Link
                key={notice.id}
                href={`/notices?notice=${notice.id}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 14,
                  padding: "13px 16px",
                  borderTop: "1px solid var(--line)",
                  color: "var(--ink)",
                  textDecoration: "none",
                  fontSize: 13,
                }}
              >
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 700 }}>{notice.title}</span>
                <span style={{ flexShrink: 0, color: "var(--ink-mute)", fontSize: 11.5 }}>{formatNoticeDate(notice.published_at)}</span>
              </Link>
            ))
          )}
        </section>

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
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "0 0 12px" }}>
          {["전체", ...FAQ_CATEGORIES].map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCatFilter(c)}
              style={{
                padding: "6px 12px",
                borderRadius: 999,
                fontSize: 12,
                fontWeight: 700,
                cursor: "pointer",
                border: "1px solid " + (catFilter === c ? "transparent" : "var(--line)"),
                background: catFilter === c ? "var(--gold)" : "#26242D",
                color: catFilter === c ? "#16151A" : "var(--ink-mute)",
              }}
            >
              {c}
            </button>
          ))}
        </div>
        {shownFaqs.map((f) => (
          <div
            key={f.id}
            id={f.id}
            className={`faq${openFaqId === f.id ? " open" : ""}`}
            onClick={() => setOpenFaqId((prev) => (prev === f.id ? null : f.id))}
          >
            <div className="q">
              {f.question}
              <span className="pm" />
            </div>
            <p className="a">
              {f.answer}
              {f.confirming && (
                <span
                  style={{
                    display: "inline-block",
                    marginLeft: 6,
                    padding: "2px 8px",
                    borderRadius: 999,
                    fontSize: 11,
                    background: "rgba(242,169,59,.14)",
                    color: "var(--gold)",
                  }}
                >
                  ⓘ 추후 보완 필요 · 정책 확정 전 안내
                </span>
              )}
            </p>
          </div>
        ))}
        {!anyVisible && (
          <div style={{ textAlign: "center", padding: 24, color: "var(--ink-mute)", fontSize: 13 }}>
            검색 결과가 없습니다.
          </div>
        )}

        <div
          ref={formRef}
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
