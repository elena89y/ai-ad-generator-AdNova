"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ReceiptText, RefreshCw, Search, Undo2, WalletCards, X } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminListResponse,
  type AdminDemoRefundResult,
  type AdminPurchase,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

type PurchaseFilters = {
  search: string;
  paymentStatus: string;
};

type PurchaseView = "orders" | "members";

type MemberPurchaseSummary = {
  userId: number;
  username: string;
  email: string;
  paidAmount: number;
  paidCount: number;
  refundedCount: number;
  latestPurchasedAt: string;
};

const STATUS_LABELS: Record<string, string> = {
  paid: "결제 완료",
  pending: "결제 대기",
  failed: "결제 실패",
  refunded: "환불 완료",
  refund_pending: "환불 신청",
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

function formatAmount(amount: number, currency: string): string {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: currency || "KRW",
    maximumFractionDigits: 0,
  }).format(amount);
}

function statusClass(status: string): string {
  if (status === "paid") return "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]";
  if (status === "pending" || status === "refund_pending") {
    return "border-[#fbbf24]/35 bg-[#fbbf24]/10 text-[#fde68a]";
  }
  if (status === "failed") return "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]";
  return "border-[#a78bfa]/35 bg-[#8b5cf6]/10 text-[#ddd6fe]";
}

export default function AdminPurchasesPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [purchases, setPurchases] = useState<AdminPurchase[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [paymentStatus, setPaymentStatus] = useState("all");
  const [appliedFilters, setAppliedFilters] = useState<PurchaseFilters>({
    search: "",
    paymentStatus: "all",
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);
  const [refundTarget, setRefundTarget] = useState<AdminPurchase | null>(null);
  const [refundReason, setRefundReason] = useState("");
  const [refundLoading, setRefundLoading] = useState(false);
  const [view, setView] = useState<PurchaseView>("orders");

  const paidAmount = useMemo(
    () => purchases.filter((purchase) => purchase.status === "paid").reduce((sum, purchase) => sum + purchase.amount, 0),
    [purchases]
  );

  const memberSummaries = useMemo(() => {
    const members = new Map<number, MemberPurchaseSummary>();

    for (const purchase of purchases) {
      const current = members.get(purchase.user_id) || {
        userId: purchase.user_id,
        username: purchase.username,
        email: purchase.email,
        paidAmount: 0,
        paidCount: 0,
        refundedCount: 0,
        latestPurchasedAt: purchase.purchased_at,
      };

      if (purchase.status === "paid") {
        current.paidAmount += purchase.amount;
        current.paidCount += 1;
      }
      if (purchase.status === "refunded") current.refundedCount += 1;
      if (new Date(purchase.purchased_at).getTime() > new Date(current.latestPurchasedAt).getTime()) {
        current.latestPurchasedAt = purchase.purchased_at;
      }
      members.set(purchase.user_id, current);
    }

    return Array.from(members.values()).sort(
      (left, right) => new Date(right.latestPurchasedAt).getTime() - new Date(left.latestPurchasedAt).getTime()
    );
  }, [purchases]);

  const loadPurchases = useCallback(async (filters: PurchaseFilters) => {
    const params = new URLSearchParams({ limit: "100" });
    const keyword = filters.search.trim();
    if (keyword) params.set("search", keyword);
    if (filters.paymentStatus !== "all") params.set("payment_status", filters.paymentStatus);

    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/purchases?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminPurchase> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "구매 이력을 불러오지 못했습니다."));
      }
      setPurchases(data.items);
      setTotal(data.total);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "구매 이력을 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadPurchases(appliedFilters);
  }, [admin, appliedFilters, loadPurchases, ready]);

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters({ search, paymentStatus });
  }

  function openRefundDialog(purchase: AdminPurchase) {
    setRefundTarget(purchase);
    setRefundReason("");
    setMessage("");
    setMessageKind(null);
  }

  async function submitRefund() {
    if (!refundTarget) return;
    const reason = refundReason.trim();
    if (!reason) {
      setMessage("환불 사유를 입력해 주세요.");
      setMessageKind("error");
      return;
    }
    if (!window.confirm(`${refundTarget.username}님의 결제를 환불할까요? 처리 후에는 되돌릴 수 없습니다.`)) return;

    setRefundLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/purchases/${refundTarget.id}/refund`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });
      const data = (await readJsonSafely(response)) as AdminDemoRefundResult | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "결제를 환불하지 못했습니다."));
      }
      setPurchases((current) => current.map((item) => (item.id === data.purchase.id ? data.purchase : item)));
      setRefundTarget(null);
      setMessage(
        data.subscription_revoked
          ? "환불을 완료하고 프리미엄 권한을 해제했습니다."
          : data.purchased_credits_revoked > 0
            ? `환불을 완료하고 구매 크레딧 ${data.purchased_credits_revoked}개를 회수했습니다.`
          : "환불을 완료했습니다."
      );
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "결제를 환불하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setRefundLoading(false);
    }
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  const canRefund = admin.role === "super_admin";

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">PAYMENTS</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">구매 이력</h1>
            <p className="mt-2 text-sm text-white/50">회원의 결제와 환불 상태를 확인합니다.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadPurchases(appliedFilters)}
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        <div className="mt-7 grid gap-3 sm:grid-cols-2">
          <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-semibold text-white/60">검색 결과</p>
              <ReceiptText size={19} className="text-[#a78bfa]" />
            </div>
            <strong className="mt-6 block text-3xl font-extrabold tabular-nums">{total.toLocaleString("ko-KR")}건</strong>
          </section>
          <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-semibold text-white/60">표시된 완료 결제액</p>
              <WalletCards size={19} className="text-[#a78bfa]" />
            </div>
            <strong className="mt-6 block text-3xl font-extrabold tabular-nums">{formatAmount(paidAmount, "KRW")}</strong>
          </section>
        </div>

        <form onSubmit={handleFilterSubmit} className="mt-7 grid gap-3 rounded-2xl border border-white/10 bg-[#102039]/90 p-4 lg:grid-cols-[minmax(0,1fr)_11rem_auto]">
          <label className="relative block">
            <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="아이디, 이메일, 결제 설명 검색"
              className="h-11 w-full border border-white/15 bg-[#0b1729] pl-10 pr-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
            />
          </label>
          <select
            value={paymentStatus}
            onChange={(event) => setPaymentStatus(event.target.value)}
            className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
          >
            <option value="all">전체 결제 상태</option>
            <option value="paid">결제 완료</option>
            <option value="pending">결제 대기</option>
            <option value="failed">결제 실패</option>
            <option value="refund_pending">환불 신청</option>
            <option value="refunded">환불 완료</option>
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

        <div className="mt-7 overflow-hidden rounded-2xl border border-white/10 bg-[#102039]/90">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <ReceiptText size={18} className="text-[#a78bfa]" />
                <h2 className="text-sm font-bold">{view === "orders" ? "결제 내역" : "회원별 결제 요약"}</h2>
              </div>
              <div className="flex border border-white/15 p-0.5 text-xs font-bold">
                <button
                  type="button"
                  onClick={() => setView("orders")}
                  className={`h-8 px-3 transition ${view === "orders" ? "bg-[#8b5cf6] text-white" : "text-white/55 hover:text-white"}`}
                >
                  결제별
                </button>
                <button
                  type="button"
                  onClick={() => setView("members")}
                  className={`h-8 px-3 transition ${view === "members" ? "bg-[#8b5cf6] text-white" : "text-white/55 hover:text-white"}`}
                >
                  회원별
                </button>
              </div>
            </div>
            <span className="text-sm text-white/50">표시된 최근 100건 기준</span>
          </div>

          <div className="overflow-x-auto">
            {view === "orders" ? (
              <table className="min-w-[1060px] w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-[#0b1729]/70 text-xs text-white/45">
                <tr>
                  <th className="px-5 py-3 font-semibold">회원</th>
                  <th className="px-5 py-3 font-semibold">구매 항목</th>
                  <th className="px-5 py-3 font-semibold">결제 금액</th>
                  <th className="px-5 py-3 font-semibold">결제 상태</th>
                  <th className="px-5 py-3 font-semibold">결제일</th>
                  <th className="px-5 py-3 font-semibold">관리</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {loading && purchases.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-14 text-center text-white/45">구매 이력을 불러오고 있습니다.</td>
                  </tr>
                ) : purchases.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-5 py-14 text-center text-white/45">조건에 맞는 구매 이력이 없습니다.</td>
                  </tr>
                ) : (
                  purchases.map((purchase) => (
                    <tr key={purchase.id} className="transition hover:bg-white/[0.025]">
                      <td className="px-5 py-4">
                        <p className="font-bold text-white">{purchase.username}</p>
                        <p className="mt-1 text-xs text-white/45">{purchase.email}</p>
                      </td>
                      <td className="px-5 py-4">
                        <p className="font-semibold text-white/80">{purchase.description}</p>
                        <p className="mt-1 text-xs text-white/40">
                          {purchase.item_type} · {purchase.provider || "-"}
                        </p>
                      </td>
                      <td className="px-5 py-4 font-bold tabular-nums text-white">{formatAmount(purchase.amount, purchase.currency)}</td>
                      <td className="px-5 py-4">
                        <span className={`inline-flex border px-2.5 py-1 text-xs font-bold ${statusClass(purchase.status)}`}>
                          {STATUS_LABELS[purchase.status] || purchase.status}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-white/55">{formatDate(purchase.purchased_at)}</td>
                      <td className="px-5 py-4">
                        {canRefund && purchase.provider === "demo" && ["subscription", "credit_pack"].includes(purchase.item_type) && purchase.status === "paid" ? (
                          <button
                            type="button"
                            onClick={() => openRefundDialog(purchase)}
                            className="inline-flex h-9 items-center gap-1.5 border border-[#f87171]/40 px-3 text-sm font-bold text-[#fecaca] transition hover:bg-[#f87171]/10"
                          >
                            <Undo2 size={15} />
                            환불
                          </button>
                        ) : (
                          <span className="text-xs text-white/35">-</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
              </table>
            ) : (
              <table className="min-w-[780px] w-full text-left text-sm">
                <thead className="border-b border-white/10 bg-[#0b1729]/70 text-xs text-white/45">
                  <tr>
                    <th className="px-5 py-3 font-semibold">회원</th>
                    <th className="px-5 py-3 font-semibold">완료 결제액</th>
                    <th className="px-5 py-3 font-semibold">완료 결제</th>
                    <th className="px-5 py-3 font-semibold">환불 완료</th>
                    <th className="px-5 py-3 font-semibold">마지막 결제일</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/10">
                  {loading && memberSummaries.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-5 py-14 text-center text-white/45">구매 이력을 불러오고 있습니다.</td>
                    </tr>
                  ) : memberSummaries.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-5 py-14 text-center text-white/45">조건에 맞는 회원 결제 내역이 없습니다.</td>
                    </tr>
                  ) : (
                    memberSummaries.map((member) => (
                      <tr key={member.userId} className="transition hover:bg-white/[0.025]">
                        <td className="px-5 py-4">
                          <p className="font-bold text-white">{member.username}</p>
                          <p className="mt-1 text-xs text-white/45">{member.email}</p>
                        </td>
                        <td className="px-5 py-4 font-bold tabular-nums text-white">{formatAmount(member.paidAmount, "KRW")}</td>
                        <td className="px-5 py-4 text-white/70">{member.paidCount.toLocaleString("ko-KR")}건</td>
                        <td className="px-5 py-4 text-white/70">{member.refundedCount.toLocaleString("ko-KR")}건</td>
                        <td className="px-5 py-4 text-white/55">{formatDate(member.latestPurchasedAt)}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {refundTarget && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-[#020617]/80 px-5 py-8" role="dialog" aria-modal="true" aria-labelledby="refund-dialog-title">
            <section className="w-full max-w-lg border border-white/15 bg-[#102039] p-6 shadow-2xl shadow-black/40">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold tracking-[0.14em] text-[#fca5a5]">DEMO REFUND</p>
                  <h2 id="refund-dialog-title" className="mt-2 text-xl font-extrabold">결제 환불</h2>
                </div>
                <button
                  type="button"
                  onClick={() => setRefundTarget(null)}
                  disabled={refundLoading}
                  className="grid size-9 place-items-center text-white/55 transition hover:bg-white/5 hover:text-white disabled:cursor-not-allowed"
                  aria-label="환불 창 닫기"
                  title="닫기"
                >
                  <X size={19} />
                </button>
              </div>
              <dl className="mt-6 grid grid-cols-[5rem_minmax(0,1fr)] gap-y-2 text-sm">
                <dt className="text-white/45">회원</dt>
                <dd className="text-white/80">{refundTarget.username} · {refundTarget.email}</dd>
                <dt className="text-white/45">결제 항목</dt>
                <dd className="text-white/80">{refundTarget.description}</dd>
                <dt className="text-white/45">결제 금액</dt>
                <dd className="font-bold text-white">{formatAmount(refundTarget.amount, refundTarget.currency)}</dd>
              </dl>
              <label className="mt-6 block">
                <span className="mb-2 block text-sm font-bold text-white/75">환불 사유</span>
                <textarea
                  value={refundReason}
                  onChange={(event) => setRefundReason(event.target.value)}
                  disabled={refundLoading}
                  maxLength={255}
                  placeholder="환불 처리 사유를 입력해 주세요."
                  className="min-h-28 w-full resize-y border border-white/15 bg-[#0b1729] px-3 py-3 text-sm leading-6 text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
                />
              </label>
              <div className="mt-6 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setRefundTarget(null)}
                  disabled={refundLoading}
                  className="h-10 border border-white/15 px-4 text-sm font-bold text-white/70 transition hover:border-white/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  취소
                </button>
                <button
                  type="button"
                  onClick={() => void submitRefund()}
                  disabled={refundLoading || !refundReason.trim()}
                  className="h-10 bg-[#ef4444] px-4 text-sm font-extrabold text-white transition hover:bg-[#f87171] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {refundLoading ? "처리 중..." : "환불 처리"}
                </button>
              </div>
            </section>
          </div>
        )}
      </section>
    </AdminShell>
  );
}
