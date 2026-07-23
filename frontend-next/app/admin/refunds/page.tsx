"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, RefreshCw, RotateCcw, X } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminListResponse,
  type AdminRefund,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

const STATUS_LABELS: Record<string, string> = {
  pending: "처리 대기",
  approved: "환불 완료",
  rejected: "환불 거절",
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

function formatAmount(amount: number): string {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(amount);
}

function statusClass(status: string): string {
  if (status === "pending") return "border-[#fbbf24]/35 bg-[#fbbf24]/10 text-[#fde68a]";
  if (status === "approved") return "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]";
  return "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]";
}

export default function AdminRefundsPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [refunds, setRefunds] = useState<AdminRefund[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("all");
  const [appliedStatus, setAppliedStatus] = useState("all");
  const [selected, setSelected] = useState<AdminRefund | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState<"approve" | "reject" | null>(null);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  const canProcessRefund = admin?.role === "super_admin";

  const loadRefunds = useCallback(async (statusFilter: string) => {
    const params = new URLSearchParams();
    if (statusFilter !== "all") params.set("status", statusFilter);

    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const query = params.toString();
      const response = await adminApiFetch(`/admin/refunds${query ? `?${query}` : ""}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminRefund> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "환불 신청 목록을 불러오지 못했습니다."));
      }
      setRefunds(data.items);
      setTotal(data.total);
      setSelected((current) => data.items.find((item) => item.id === current?.id) || null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "환불 신청 목록을 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadRefunds(appliedStatus);
  }, [admin, appliedStatus, loadRefunds, ready]);

  useEffect(() => {
    setRejectReason("");
  }, [selected]);

  async function processRefund(action: "approve" | "reject") {
    if (!selected) return;
    const reason = rejectReason.trim();
    if (action === "reject" && !reason) {
      setMessage("거절 사유를 입력해 주세요.");
      setMessageKind("error");
      return;
    }
    const actionLabel = action === "approve" ? "승인" : "거절";
    if (!window.confirm(`${selected.username}님의 환불 신청을 ${actionLabel}할까요?`)) return;

    setProcessing(action);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/refunds/${selected.id}/${action}`, {
        method: "POST",
        headers: action === "reject" ? { "Content-Type": "application/json" } : undefined,
        body: action === "reject" ? JSON.stringify({ reason }) : undefined,
      });
      const data = (await readJsonSafely(response)) as AdminRefund | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "환불 신청을 처리하지 못했습니다."));
      }
      setRefunds((current) => current.map((item) => (item.id === data.id ? data : item)));
      setSelected(data);
      setMessage(`환불 신청을 ${actionLabel}했습니다.`);
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "환불 신청을 처리하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setProcessing(null);
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
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">REFUNDS</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">환불 관리</h1>
            <p className="mt-2 text-sm text-white/50">회원이 신청한 데모 결제 환불을 처리합니다.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadRefunds(appliedStatus)}
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        {!canProcessRefund && (
          <p className="mt-6 border border-[#a78bfa]/30 bg-[#8b5cf6]/10 px-4 py-3 text-sm text-[#ddd6fe]">
            운영자는 환불 신청을 조회할 수 있습니다. 승인과 거절은 최고 관리자만 할 수 있습니다.
          </p>
        )}

        <div className="mt-7 grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem]">
          <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-semibold text-white/60">검색 결과</p>
              <RotateCcw size={19} className="text-[#a78bfa]" />
            </div>
            <strong className="mt-6 block text-3xl font-extrabold tabular-nums">{total.toLocaleString("ko-KR")}건</strong>
          </section>
          <label className="rounded-2xl border border-white/10 bg-[#102039]/90 p-4">
            <span className="mb-2 block text-xs font-bold text-white/50">환불 상태</span>
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setAppliedStatus(event.target.value);
              }}
              className="h-10 w-full border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
            >
              <option value="all">전체 상태</option>
              <option value="pending">처리 대기</option>
              <option value="approved">환불 완료</option>
              <option value="rejected">환불 거절</option>
            </select>
          </label>
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

        <div className="mt-7 grid gap-3 xl:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.9fr)]">
          <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#102039]/90">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
              <div className="flex items-center gap-2">
                <RotateCcw size={18} className="text-[#a78bfa]" />
                <h2 className="text-sm font-bold">환불 신청 목록</h2>
              </div>
              <span className="text-sm text-white/50">총 {total.toLocaleString("ko-KR")}건</span>
            </div>
            <div className="divide-y divide-white/10">
              {loading && refunds.length === 0 ? (
                <p className="px-5 py-14 text-center text-sm text-white/45">환불 신청을 불러오고 있습니다.</p>
              ) : refunds.length === 0 ? (
                <p className="px-5 py-14 text-center text-sm text-white/45">조건에 맞는 환불 신청이 없습니다.</p>
              ) : (
                refunds.map((refund) => (
                  <button
                    key={refund.id}
                    type="button"
                    onClick={() => setSelected(refund)}
                    className={`w-full px-5 py-4 text-left transition hover:bg-white/[0.025] ${
                      selected?.id === refund.id ? "bg-[#8b5cf6]/10" : ""
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-bold text-white">{refund.description}</p>
                        <p className="mt-1 truncate text-xs text-white/45">{refund.username} · {refund.email}</p>
                      </div>
                      <span className={`shrink-0 border px-2 py-1 text-[11px] font-bold ${statusClass(refund.status)}`}>
                        {STATUS_LABELS[refund.status] || refund.status}
                      </span>
                    </div>
                    <p className="mt-3 text-sm font-bold text-white/75">{formatAmount(refund.amount)}</p>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-white/45">{refund.reason}</p>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-[#102039]/90">
            {!selected ? (
              <div className="grid min-h-80 place-items-center px-5 text-center text-sm text-white/45">처리할 환불 신청을 선택해 주세요.</div>
            ) : (
              <div className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold tracking-[0.12em] text-[#a78bfa]">REFUND #{selected.id}</p>
                    <h2 className="mt-2 text-xl font-extrabold">{selected.description}</h2>
                  </div>
                  <span className={`border px-2.5 py-1 text-xs font-bold ${statusClass(selected.status)}`}>
                    {STATUS_LABELS[selected.status] || selected.status}
                  </span>
                </div>

                <dl className="mt-6 grid grid-cols-[5rem_minmax(0,1fr)] gap-y-2 text-sm">
                  <dt className="text-white/45">회원</dt>
                  <dd className="text-white/80">{selected.username}</dd>
                  <dt className="text-white/45">이메일</dt>
                  <dd className="truncate text-white/80">{selected.email}</dd>
                  <dt className="text-white/45">환불 금액</dt>
                  <dd className="font-bold text-white">{formatAmount(selected.amount)}</dd>
                  <dt className="text-white/45">신청일</dt>
                  <dd className="text-white/80">{formatDate(selected.requested_at)}</dd>
                </dl>

                <div className="mt-6 border-y border-white/10 py-5">
                  <p className="mb-2 text-xs font-bold text-white/45">신청 사유</p>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-white/75">{selected.reason}</p>
                </div>

                {selected.status === "rejected" && selected.rejection_reason && (
                  <div className="mt-5 border border-[#f87171]/30 bg-[#f87171]/10 px-4 py-3 text-sm text-[#fecaca]">
                    거절 사유: {selected.rejection_reason}
                  </div>
                )}

                {selected.status === "pending" && canProcessRefund && (
                  <div className="mt-6">
                    <label className="mb-2 block text-sm font-bold text-white/75" htmlFor="refund-reject-reason">거절 사유</label>
                    <textarea
                      id="refund-reject-reason"
                      value={rejectReason}
                      onChange={(event) => setRejectReason(event.target.value)}
                      disabled={processing !== null}
                      maxLength={500}
                      placeholder="거절할 경우에만 사유를 입력해 주세요."
                      className="min-h-24 w-full resize-y border border-white/15 bg-[#0b1729] px-3 py-3 text-sm leading-6 text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
                    />
                    <div className="mt-4 flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => void processRefund("reject")}
                        disabled={processing !== null || !rejectReason.trim()}
                        className="inline-flex h-10 items-center gap-2 border border-[#f87171]/45 px-4 text-sm font-bold text-[#fecaca] transition hover:bg-[#f87171]/10 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <X size={16} />
                        {processing === "reject" ? "처리 중..." : "거절"}
                      </button>
                      <button
                        type="button"
                        onClick={() => void processRefund("approve")}
                        disabled={processing !== null}
                        className="inline-flex h-10 items-center gap-2 bg-[#8b5cf6] px-4 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <Check size={16} />
                        {processing === "approve" ? "처리 중..." : "승인"}
                      </button>
                    </div>
                  </div>
                )}

                {selected.status !== "pending" && (
                  <p className="mt-6 text-sm text-white/45">처리일: {formatDate(selected.processed_at)}</p>
                )}
              </div>
            )}
          </section>
        </div>
      </section>
    </AdminShell>
  );
}
