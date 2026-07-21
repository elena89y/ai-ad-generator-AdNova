"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, MessageSquareMore, RefreshCw, Search, Send } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminInquiry,
  type AdminInquiryStatus,
  type AdminListResponse,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

type InquiryFilters = {
  search: string;
  status: "all" | AdminInquiryStatus;
};

const STATUS_LABELS: Record<AdminInquiryStatus, string> = {
  pending: "답변 대기",
  in_progress: "처리 중",
  answered: "답변 완료",
  closed: "종료",
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusClass(status: AdminInquiryStatus): string {
  if (status === "pending") return "border-[#fbbf24]/35 bg-[#fbbf24]/10 text-[#fde68a]";
  if (status === "in_progress") return "border-[#60a5fa]/35 bg-[#60a5fa]/10 text-[#bfdbfe]";
  if (status === "answered") return "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]";
  return "border-[#a78bfa]/35 bg-[#8b5cf6]/10 text-[#ddd6fe]";
}

export default function AdminInquiriesPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [inquiries, setInquiries] = useState<AdminInquiry[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<InquiryFilters["status"]>("all");
  const [appliedFilters, setAppliedFilters] = useState<InquiryFilters>({ search: "", status: "all" });
  const [selected, setSelected] = useState<AdminInquiry | null>(null);
  const [draftStatus, setDraftStatus] = useState<AdminInquiryStatus>("pending");
  const [answerDraft, setAnswerDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState<"status" | "answer" | null>(null);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  const loadInquiries = useCallback(async (filters: InquiryFilters) => {
    const params = new URLSearchParams({ limit: "100" });
    const keyword = filters.search.trim();
    if (keyword) params.set("search", keyword);
    if (filters.status !== "all") params.set("inquiry_status", filters.status);

    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/inquiries?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminInquiry> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "문의 목록을 불러오지 못했습니다."));
      }
      setInquiries(data.items);
      setTotal(data.total);
      setSelected((current) => data.items.find((item) => item.id === current?.id) || null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "문의 목록을 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadInquiries(appliedFilters);
  }, [admin, appliedFilters, loadInquiries, ready]);

  useEffect(() => {
    if (!selected) return;
    setDraftStatus(selected.status);
    setAnswerDraft(selected.answer || "");
  }, [selected]);

  function selectInquiry(inquiry: AdminInquiry) {
    setSelected(inquiry);
    setMessage("");
    setMessageKind(null);
  }

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters({ search, status });
  }

  async function updateInquiry(
    path: "status" | "answer",
    body: { status: AdminInquiryStatus } | { answer: string },
    successMessage: string
  ) {
    if (!selected) return;

    setProcessing(path);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/inquiries/${selected.id}/${path}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await readJsonSafely(response)) as AdminInquiry | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "문의 정보를 변경하지 못했습니다."));
      }

      setInquiries((current) => current.map((item) => (item.id === data.id ? data : item)));
      setSelected(data);
      setDraftStatus(data.status);
      setAnswerDraft(data.answer || "");
      setMessage(successMessage);
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "문의 정보를 변경하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setProcessing(null);
    }
  }

  function saveStatus() {
    if (!selected || draftStatus === selected.status) return;
    void updateInquiry("status", { status: draftStatus }, "문의 처리 상태를 변경했습니다.");
  }

  function saveAnswer() {
    const answer = answerDraft.trim();
    if (!answer) {
      setMessage("답변 내용을 입력해 주세요.");
      setMessageKind("error");
      return;
    }
    void updateInquiry("answer", { answer }, "문의 답변을 저장했습니다.");
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">SUPPORT</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">1:1 문의</h1>
            <p className="mt-2 text-sm text-white/50">회원 문의를 확인하고 답변을 등록합니다.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadInquiries(appliedFilters)}
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        <form onSubmit={handleFilterSubmit} className="mt-7 grid gap-3 border border-white/10 bg-[#102039]/90 p-4 lg:grid-cols-[minmax(0,1fr)_10rem_auto]">
          <label className="relative block">
            <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="제목, 내용, 아이디, 이메일 검색"
              className="h-11 w-full border border-white/15 bg-[#0b1729] pl-10 pr-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
            />
          </label>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as InquiryFilters["status"])}
            className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
          >
            <option value="all">전체 상태</option>
            <option value="pending">답변 대기</option>
            <option value="in_progress">처리 중</option>
            <option value="answered">답변 완료</option>
            <option value="closed">종료</option>
          </select>
          <button
            type="submit"
            disabled={loading}
            className="h-11 bg-[#8b5cf6] px-5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
          >
            적용
          </button>
        </form>

        {message && (
          <p
            role={messageKind === "error" ? "alert" : "status"}
            className={`mt-5 border px-4 py-3 text-sm ${
              messageKind === "error"
                ? "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]"
                : "border-[#a78bfa]/30 bg-[#8b5cf6]/10 text-[#ddd6fe]"
            }`}
          >
            {message}
          </p>
        )}

        <div className="mt-7 grid gap-3 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
          <section className="overflow-hidden border border-white/10 bg-[#102039]/90">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex items-center gap-2">
                <MessageSquareMore size={18} className="text-[#a78bfa]" />
                <h2 className="text-sm font-bold">문의 목록</h2>
              </div>
              <span className="text-sm text-white/50">총 {total.toLocaleString("ko-KR")}건</span>
            </div>

            <div className="divide-y divide-white/10">
              {loading && inquiries.length === 0 ? (
                <p className="px-5 py-14 text-center text-sm text-white/45">문의 목록을 불러오고 있습니다.</p>
              ) : inquiries.length === 0 ? (
                <p className="px-5 py-14 text-center text-sm text-white/45">조건에 맞는 문의가 없습니다.</p>
              ) : (
                inquiries.map((inquiry) => (
                  <button
                    key={inquiry.id}
                    type="button"
                    onClick={() => selectInquiry(inquiry)}
                    className={`w-full px-5 py-4 text-left transition hover:bg-white/[0.025] ${
                      selected?.id === inquiry.id ? "bg-[#8b5cf6]/10" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-bold text-white">{inquiry.title}</p>
                        <p className="mt-1 truncate text-xs text-white/45">{inquiry.username} · {inquiry.email}</p>
                      </div>
                      <span className={`shrink-0 border px-2 py-1 text-[11px] font-bold ${statusClass(inquiry.status)}`}>
                        {STATUS_LABELS[inquiry.status]}
                      </span>
                    </div>
                    <p className="mt-3 line-clamp-2 text-sm leading-6 text-white/55">{inquiry.content}</p>
                    <p className="mt-3 text-xs text-white/35">{formatDate(inquiry.created_at)}</p>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="border border-white/10 bg-[#102039]/90">
            {!selected ? (
              <div className="grid min-h-80 place-items-center px-5 text-center text-sm text-white/45">
                확인할 문의를 선택해 주세요.
              </div>
            ) : (
              <div className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold tracking-[0.12em] text-[#a78bfa]">INQUIRY #{selected.id}</p>
                    <h2 className="mt-2 text-xl font-extrabold">{selected.title}</h2>
                  </div>
                  <span className={`border px-2.5 py-1 text-xs font-bold ${statusClass(selected.status)}`}>
                    {STATUS_LABELS[selected.status]}
                  </span>
                </div>

                <dl className="mt-6 grid grid-cols-[4.5rem_minmax(0,1fr)] gap-y-2 text-sm">
                  <dt className="text-white/45">문의자</dt>
                  <dd className="truncate text-white/80">{selected.username}</dd>
                  <dt className="text-white/45">이메일</dt>
                  <dd className="truncate text-white/80">{selected.email}</dd>
                  <dt className="text-white/45">접수일</dt>
                  <dd className="text-white/80">{formatDate(selected.created_at)}</dd>
                </dl>

                <div className="mt-6 border-y border-white/10 py-5">
                  <p className="mb-2 text-xs font-bold text-white/45">문의 내용</p>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-white/75">{selected.content}</p>
                </div>

                <div className="mt-6">
                  <label className="mb-2 block text-sm font-bold text-white/75" htmlFor="inquiry-status">처리 상태</label>
                  <div className="flex gap-2">
                    <select
                      id="inquiry-status"
                      value={draftStatus}
                      disabled={processing !== null}
                      onChange={(event) => setDraftStatus(event.target.value as AdminInquiryStatus)}
                      className="h-10 min-w-0 flex-1 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <option value="pending">답변 대기</option>
                      <option value="in_progress">처리 중</option>
                      <option value="answered">답변 완료</option>
                      <option value="closed">종료</option>
                    </select>
                    <button
                      type="button"
                      onClick={saveStatus}
                      disabled={processing !== null || draftStatus === selected.status}
                      className="inline-flex h-10 items-center gap-1.5 border border-[#a78bfa]/50 px-3 text-sm font-bold text-[#ddd6fe] transition hover:bg-[#8b5cf6]/15 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Check size={16} />
                      저장
                    </button>
                  </div>
                </div>

                <div className="mt-6">
                  <label className="mb-2 block text-sm font-bold text-white/75" htmlFor="inquiry-answer">답변</label>
                  <textarea
                    id="inquiry-answer"
                    value={answerDraft}
                    disabled={processing !== null}
                    onChange={(event) => setAnswerDraft(event.target.value)}
                    placeholder="회원에게 전달할 답변을 입력해 주세요."
                    className="min-h-40 w-full resize-y border border-white/15 bg-[#0b1729] px-3 py-3 text-sm leading-6 text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <div className="mt-3 flex justify-end">
                    <button
                      type="button"
                      onClick={saveAnswer}
                      disabled={processing !== null || !answerDraft.trim()}
                      className="inline-flex h-10 items-center gap-2 bg-[#8b5cf6] px-4 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <Send size={16} />
                      {processing === "answer" ? "저장 중..." : "답변 저장"}
                    </button>
                  </div>
                </div>
              </div>
            )}
          </section>
        </div>
      </section>
    </AdminShell>
  );
}
