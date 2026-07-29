"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { Check, Flag, RefreshCw, Search } from "lucide-react";
import { useRouter } from "next/navigation";

import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminListResponse,
  type AdminReport,
  type AdminReportStatus,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

type ReportFilters = {
  search: string;
  status: "all" | AdminReportStatus;
};

const STATUS_LABELS: Record<AdminReportStatus, string> = {
  pending: "접수됨",
  in_progress: "확인 중",
  resolved: "처리 완료",
  rejected: "처리 불가",
};

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusClass(status: AdminReportStatus): string {
  if (status === "pending") return "border-[#fbbf24]/35 bg-[#fbbf24]/10 text-[#fde68a]";
  if (status === "in_progress") return "border-[#60a5fa]/35 bg-[#60a5fa]/10 text-[#bfdbfe]";
  if (status === "resolved") return "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]";
  return "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]";
}

function matchesReportFilters(report: AdminReport, filters: ReportFilters): boolean {
  if (filters.status !== "all" && report.status !== filters.status) return false;
  const keyword = filters.search.trim().toLowerCase();
  if (!keyword) return true;
  return [report.title, report.content, report.category, report.username, report.email]
    .join(" ")
    .toLowerCase()
    .includes(keyword);
}

export default function AdminReportsPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<ReportFilters["status"]>("all");
  const [appliedFilters, setAppliedFilters] = useState<ReportFilters>({ search: "", status: "all" });
  const [selected, setSelected] = useState<AdminReport | null>(null);
  const [draftStatus, setDraftStatus] = useState<AdminReportStatus>("pending");
  const [adminNote, setAdminNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  const loadReports = useCallback(async (filters: ReportFilters) => {
    const params = new URLSearchParams({ limit: "100" });
    const keyword = filters.search.trim();
    if (keyword) params.set("search", keyword);
    if (filters.status !== "all") params.set("report_status", filters.status);

    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/reports?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminReport> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "신고 목록을 불러오지 못했습니다."));
      }
      setReports(data.items);
      setTotal(data.total);
      setSelected((current) => data.items.find((item) => item.id === current?.id) || null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "신고 목록을 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadReports(appliedFilters);
  }, [admin, appliedFilters, loadReports, ready]);

  useEffect(() => {
    if (!selected) return;
    setDraftStatus(selected.status);
    setAdminNote(selected.admin_note || "");
  }, [selected]);

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters({ search, status });
  }

  async function saveReport() {
    if (!selected) return;

    setSaving(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/reports/${selected.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: draftStatus,
          admin_note: adminNote.trim() || null,
        }),
      });
      const data = (await readJsonSafely(response)) as AdminReport | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "신고 처리 내용을 저장하지 못했습니다."));
      }
      await loadReports(appliedFilters);
      setSelected(matchesReportFilters(data, appliedFilters) ? data : null);
      setMessage("신고 처리 내용을 저장했습니다.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "신고 처리 내용을 저장하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setSaving(false);
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
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">SAFETY</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">신고 관리</h1>
            <p className="mt-2 text-sm text-white/50">회원이 접수한 신고를 확인하고 처리 상태를 기록합니다.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadReports(appliedFilters)}
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        <form onSubmit={handleFilterSubmit} className="mt-7 grid gap-3 rounded-2xl border border-white/10 bg-[#102039]/90 p-4 lg:grid-cols-[minmax(0,1fr)_10rem_auto]">
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
            onChange={(event) => setStatus(event.target.value as ReportFilters["status"])}
            className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
          >
            <option value="all">전체 상태</option>
            <option value="pending">접수됨</option>
            <option value="in_progress">확인 중</option>
            <option value="resolved">처리 완료</option>
            <option value="rejected">처리 불가</option>
          </select>
          <button type="submit" disabled={loading} className="h-11 bg-[#8b5cf6] px-5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60">
            적용
          </button>
        </form>

        {message && (
          <p role={messageKind === "error" ? "alert" : "status"} className={`mt-5 border px-4 py-3 text-sm ${messageKind === "error" ? "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]" : "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]"}`}>
            {message}
          </p>
        )}

        <div className="mt-7 grid gap-3 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
          <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#102039]/90">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex items-center gap-2">
                <Flag size={18} className="text-[#a78bfa]" />
                <h2 className="text-sm font-bold">신고 목록</h2>
              </div>
              <span className="text-sm text-white/50">총 {total.toLocaleString("ko-KR")}건</span>
            </div>
            <div className="divide-y divide-white/10">
              {loading && reports.length === 0 ? (
                <p className="px-5 py-14 text-center text-sm text-white/45">신고 목록을 불러오고 있습니다.</p>
              ) : reports.length === 0 ? (
                <p className="px-5 py-14 text-center text-sm text-white/45">조건에 맞는 신고가 없습니다.</p>
              ) : (
                reports.map((report) => (
                  <button key={report.id} type="button" onClick={() => { setSelected(report); setMessage(""); setMessageKind(null); }} className={`w-full px-5 py-4 text-left transition hover:bg-white/[0.025] ${selected?.id === report.id ? "bg-[#8b5cf6]/10" : ""}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-bold text-white">{report.title}</p>
                        <p className="mt-1 truncate text-xs text-white/45">{report.username} · {report.email}</p>
                      </div>
                      <span className={`shrink-0 border px-2 py-1 text-[11px] font-bold ${statusClass(report.status)}`}>{STATUS_LABELS[report.status]}</span>
                    </div>
                    <p className="mt-3 line-clamp-2 text-sm leading-6 text-white/55">{report.content}</p>
                    <p className="mt-3 text-xs text-white/35">{formatDate(report.created_at)}</p>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-[#102039]/90">
            {!selected ? (
              <div className="grid min-h-80 place-items-center px-5 text-center text-sm text-white/45">확인할 신고를 선택해 주세요.</div>
            ) : (
              <div className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold tracking-[0.12em] text-[#a78bfa]">REPORT #{selected.id}</p>
                    <h2 className="mt-2 text-xl font-extrabold">{selected.title}</h2>
                  </div>
                  <span className={`border px-2.5 py-1 text-xs font-bold ${statusClass(selected.status)}`}>{STATUS_LABELS[selected.status]}</span>
                </div>
                <dl className="mt-6 grid grid-cols-[5rem_minmax(0,1fr)] gap-y-2 text-sm">
                  <dt className="text-white/45">신고자</dt><dd className="truncate text-white/80">{selected.username}</dd>
                  <dt className="text-white/45">이메일</dt><dd className="truncate text-white/80">{selected.email}</dd>
                  <dt className="text-white/45">유형</dt><dd className="text-white/80">{selected.category}</dd>
                  <dt className="text-white/45">광고</dt><dd className="text-white/80">{selected.advertisement_id ? `광고 #${selected.advertisement_id}` : "연결된 광고 없음"}</dd>
                  <dt className="text-white/45">접수일</dt><dd className="text-white/80">{formatDate(selected.created_at)}</dd>
                </dl>
                <div className="mt-6 border-y border-white/10 py-5">
                  <p className="mb-2 text-xs font-bold text-white/45">신고 내용</p>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-white/75">{selected.content}</p>
                </div>
                <div className="mt-6">
                  <label className="mb-2 block text-sm font-bold text-white/75" htmlFor="report-status">처리 상태</label>
                  <select id="report-status" value={draftStatus} disabled={saving} onChange={(event) => setDraftStatus(event.target.value as AdminReportStatus)} className="h-10 w-full border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60">
                    <option value="pending">접수됨</option>
                    <option value="in_progress">확인 중</option>
                    <option value="resolved">처리 완료</option>
                    <option value="rejected">처리 불가</option>
                  </select>
                </div>
                <div className="mt-5">
                  <label className="mb-2 block text-sm font-bold text-white/75" htmlFor="report-note">관리자 메모</label>
                  <textarea id="report-note" value={adminNote} disabled={saving} onChange={(event) => setAdminNote(event.target.value)} maxLength={5000} placeholder="처리 내용이나 확인 사항을 기록해 주세요." className="min-h-36 w-full resize-y border border-white/15 bg-[#0b1729] px-3 py-3 text-sm leading-6 text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60" />
                </div>
                <div className="mt-3 flex justify-end">
                  <button type="button" onClick={() => void saveReport()} disabled={saving} className="inline-flex h-10 items-center gap-2 bg-[#8b5cf6] px-4 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60">
                    <Check size={16} />{saving ? "저장 중..." : "처리 내용 저장"}
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>
      </section>
    </AdminShell>
  );
}
