"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, MessageCircleQuestion, RefreshCw, X } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import { type AdminFaqCandidate, type AdminListResponse, adminApiFetch } from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

/* FAQ 후보 큐 — 담당: 한의정.
   관리자가 답변한 1:1 문의에서 "FAQ 후보로 등록"한 항목을 검토·승인/기각한다.
   승인된 후보를 실제 KB(faq_ko.yaml)에 반영하는 것은 후속(수동/스크립트) 단계. */

const STATUS_FILTERS = [
  { key: "pending", label: "대기 중" },
  { key: "approved", label: "승인됨" },
  { key: "dismissed", label: "기각됨" },
  { key: "", label: "전체" },
] as const;

const STATUS_LABELS: Record<string, string> = {
  pending: "대기 중",
  approved: "승인됨",
  dismissed: "기각됨",
};

function statusClass(status: string): string {
  if (status === "approved") return "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#9ef5c9]";
  if (status === "dismissed") return "border-white/20 bg-white/5 text-white/50";
  return "border-[#a78bfa]/35 bg-[#8b5cf6]/10 text-[#ddd6fe]";
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export default function AdminFaqPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [candidates, setCandidates] = useState<AdminFaqCandidate[]>([]);
  const [filter, setFilter] = useState<string>("pending");
  const [loading, setLoading] = useState(false);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  const loadCandidates = useCallback(async () => {
    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const query = filter ? `?candidate_status=${encodeURIComponent(filter)}` : "";
      const response = await adminApiFetch(`/admin/faq-candidates${query}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminFaqCandidate> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "FAQ 후보를 불러오지 못했습니다."));
      }
      setCandidates(data.items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "FAQ 후보를 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadCandidates();
  }, [admin, loadCandidates, ready]);

  async function review(candidate: AdminFaqCandidate, status: "approved" | "dismissed") {
    setProcessingId(candidate.id);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/faq-candidates/${candidate.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      const data = (await readJsonSafely(response)) as AdminFaqCandidate | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "FAQ 후보를 처리하지 못했습니다."));
      }
      setMessage(status === "approved" ? "FAQ 후보를 승인했습니다." : "FAQ 후보를 기각했습니다.");
      setMessageKind("success");
      // 현재 필터에 맞게 목록 갱신 (필터가 걸려 있으면 항목이 빠질 수 있으므로 재조회)
      void loadCandidates();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "FAQ 후보를 처리하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setProcessingId(null);
    }
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">KNOWLEDGE</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">FAQ 관리</h1>
            <p className="mt-2 text-sm text-white/50">
              답변한 1:1 문의를 FAQ 후보로 등록하고 검토합니다. 승인된 후보는 지식베이스에 반영됩니다.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadCandidates()}
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-white/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key || "all"}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`h-9 rounded-full border px-4 text-sm font-semibold transition ${
                filter === f.key
                  ? "border-transparent bg-[#8b5cf6] text-white"
                  : "border-white/15 text-white/60 hover:border-white/30 hover:text-white"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

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

        <div className="mt-6 space-y-3">
          {loading && candidates.length === 0 ? (
            <p className="border border-white/10 bg-[#102039]/90 px-5 py-14 text-center text-sm text-white/45">
              FAQ 후보를 불러오고 있습니다.
            </p>
          ) : candidates.length === 0 ? (
            <p className="border border-white/10 bg-[#102039]/90 px-5 py-14 text-center text-sm text-white/45">
              조건에 맞는 FAQ 후보가 없습니다.
            </p>
          ) : (
            candidates.map((candidate) => (
              <article
                key={candidate.id}
                className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full border border-white/15 px-2.5 py-0.5 text-xs text-white/55">
                    {candidate.category}
                  </span>
                  <span className={`rounded-full border px-2.5 py-0.5 text-xs ${statusClass(candidate.status)}`}>
                    {STATUS_LABELS[candidate.status] ?? candidate.status}
                  </span>
                  <span className="ml-auto text-xs text-white/40">{formatDate(candidate.created_at)}</span>
                </div>
                <div className="mt-4 flex items-start gap-2">
                  <MessageCircleQuestion size={18} className="mt-0.5 shrink-0 text-[#a78bfa]" />
                  <p className="text-sm font-bold text-white">{candidate.question}</p>
                </div>
                <p className="mt-2 whitespace-pre-line pl-7 text-sm leading-6 text-white/65">
                  {candidate.answer}
                </p>
                {candidate.status === "pending" && (
                  <div className="mt-4 flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => void review(candidate, "dismissed")}
                      disabled={processingId !== null}
                      className="inline-flex h-9 items-center gap-1.5 border border-white/15 px-3.5 text-sm font-bold text-white/70 transition hover:border-white/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <X size={15} />
                      기각
                    </button>
                    <button
                      type="button"
                      onClick={() => void review(candidate, "approved")}
                      disabled={processingId !== null}
                      className="inline-flex h-9 items-center gap-1.5 bg-[#8b5cf6] px-3.5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <Check size={15} />
                      {processingId === candidate.id ? "처리 중..." : "승인"}
                    </button>
                  </div>
                )}
              </article>
            ))
          )}
        </div>
      </section>
    </AdminShell>
  );
}
