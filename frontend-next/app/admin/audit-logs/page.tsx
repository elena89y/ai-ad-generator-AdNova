"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, ScrollText, Search, ShieldCheck } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminAuditLog,
  type AdminListResponse,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

const ACTION_LABELS: Record<string, string> = {
  "admin.account_created": "관리자 계정 지정",
  "admin.role_updated": "관리자 권한 변경",
  "admin.status_updated": "관리자 계정 상태 변경",
  "admin.password_changed": "관리자 비밀번호 변경",
  "user.status_updated": "회원 계정 상태 변경",
  "user.subscription_updated": "회원 플랜 변경",
  "purchase.refunded": "결제 환불",
  "refund.approved": "환불 신청 승인",
  "refund.rejected": "환불 신청 거절",
  "inquiry.status_updated": "문의 상태 변경",
  "inquiry.answered": "문의 답변 등록",
};

const TARGET_LABELS: Record<string, string> = {
  admin_account: "관리자 계정",
  admin: "관리자 계정",
  user: "회원",
  purchase: "결제",
  refund: "환불 신청",
  inquiry: "문의",
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

function getActionLabel(action: string): string {
  return ACTION_LABELS[action] || action;
}

export default function AdminAuditLogsPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [logs, setLogs] = useState<AdminAuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState("all");
  const [appliedAction, setAppliedAction] = useState("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const loadLogs = useCallback(async (actionFilter: string) => {
    const params = new URLSearchParams({ limit: "100" });
    if (actionFilter !== "all") params.set("action", actionFilter);

    setLoading(true);
    setMessage("");
    try {
      const response = await adminApiFetch(`/admin/audit-logs?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminAuditLog> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "감사 로그를 불러오지 못했습니다."));
      }
      setLogs(data.items);
      setTotal(data.total);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "감사 로그를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadLogs(appliedAction);
  }, [admin, appliedAction, loadLogs, ready]);

  const filteredLogs = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return logs;

    return logs.filter((log) =>
      [
        getActionLabel(log.action),
        log.admin_username,
        TARGET_LABELS[log.target_type] || log.target_type,
        String(log.target_id),
        log.detail || "",
      ]
        .join(" ")
        .toLowerCase()
        .includes(keyword)
    );
  }, [logs, search]);

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">AUDIT</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">감사 로그</h1>
            <p className="mt-2 text-sm text-white/50">관리자 작업 내역을 시간순으로 확인합니다.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadLogs(appliedAction)}
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        <div className="mt-7 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(14rem,0.8fr)_12rem]">
          <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-semibold text-white/60">검색 결과</p>
              <ShieldCheck size={19} className="text-[#a78bfa]" />
            </div>
            <strong className="mt-6 block text-3xl font-extrabold tabular-nums">{filteredLogs.length.toLocaleString("ko-KR")}건</strong>
            <p className="mt-2 text-xs text-white/40">불러온 {logs.length.toLocaleString("ko-KR")}건 / 전체 {total.toLocaleString("ko-KR")}건</p>
          </section>
          <label className="relative rounded-2xl border border-white/10 bg-[#102039]/90 p-4">
            <span className="mb-2 block text-xs font-bold text-white/50">텍스트 검색</span>
            <Search size={16} className="pointer-events-none absolute bottom-[1.45rem] left-7 text-white/35" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="관리자, 작업, 대상, 내용"
              className="h-10 w-full border border-white/15 bg-[#0b1729] pl-9 pr-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
            />
          </label>
          <label className="rounded-2xl border border-white/10 bg-[#102039]/90 p-4">
            <span className="mb-2 block text-xs font-bold text-white/50">작업 종류</span>
            <select
              value={action}
              onChange={(event) => {
                setAction(event.target.value);
                setAppliedAction(event.target.value);
              }}
              className="h-10 w-full border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
            >
              <option value="all">전체 작업</option>
              {Object.entries(ACTION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
        </div>

        {message && (
          <p role="alert" className="mt-5 border border-[#f87171]/35 bg-[#f87171]/10 px-4 py-3 text-sm text-[#fecaca]">
            {message}
          </p>
        )}

        <div className="mt-7 overflow-hidden rounded-2xl border border-white/10 bg-[#102039]/90">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div className="flex items-center gap-2">
              <ScrollText size={18} className="text-[#a78bfa]" />
              <h2 className="text-sm font-bold">작업 기록</h2>
            </div>
            <span className="text-sm text-white/50">불러온 최근 100건 내 검색</span>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-[900px] w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-[#0b1729]/70 text-xs text-white/45">
                <tr>
                  <th className="px-5 py-3 font-semibold">작업</th>
                  <th className="px-5 py-3 font-semibold">관리자</th>
                  <th className="px-5 py-3 font-semibold">대상</th>
                  <th className="px-5 py-3 font-semibold">추가 정보</th>
                  <th className="px-5 py-3 font-semibold">처리 시간</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {loading && logs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-white/45">감사 로그를 불러오고 있습니다.</td>
                  </tr>
                ) : filteredLogs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-white/45">조건에 맞는 감사 로그가 없습니다.</td>
                  </tr>
                ) : (
                  filteredLogs.map((log) => (
                    <tr key={log.id} className="transition hover:bg-white/[0.025]">
                      <td className="px-5 py-4 font-semibold text-white">{getActionLabel(log.action)}</td>
                      <td className="px-5 py-4 text-white/75">{log.admin_username}</td>
                      <td className="px-5 py-4 text-white/65">
                        {(TARGET_LABELS[log.target_type] || log.target_type)} #{log.target_id}
                      </td>
                      <td className="max-w-72 break-all px-5 py-4 text-xs leading-5 text-white/45">{log.detail || "-"}</td>
                      <td className="px-5 py-4 text-white/55">{formatDate(log.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </AdminShell>
  );
}
