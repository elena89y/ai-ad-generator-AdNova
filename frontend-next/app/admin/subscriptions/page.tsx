"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { CreditCard, RefreshCw, Search, TimerReset } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminListResponse,
  type AdminSubscription,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

type PlanFilter = "all" | "free" | "premium";
type SubscriptionFilters = {
  search: string;
  plan: PlanFilter;
  status: string;
};

const STATUS_LABELS: Record<string, string> = {
  active: "이용 중",
  inactive: "비활성",
  canceled: "해지됨",
  expired: "만료됨",
};

function formatDate(value: string | null): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function statusClass(status: string): string {
  if (status === "active") return "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]";
  if (status === "inactive") return "border-[#94a3b8]/35 bg-[#94a3b8]/10 text-[#cbd5e1]";
  return "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]";
}

export default function AdminSubscriptionsPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [subscriptions, setSubscriptions] = useState<AdminSubscription[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [plan, setPlan] = useState<PlanFilter>("all");
  const [status, setStatus] = useState("all");
  const [appliedFilters, setAppliedFilters] = useState<SubscriptionFilters>({
    search: "",
    plan: "all",
    status: "all",
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const scheduledCancellationCount = useMemo(
    () => subscriptions.filter((subscription) => subscription.cancel_at_period_end).length,
    [subscriptions]
  );

  const loadSubscriptions = useCallback(async (filters: SubscriptionFilters) => {
    const params = new URLSearchParams({ limit: "100" });
    const keyword = filters.search.trim();
    if (keyword) params.set("search", keyword);
    if (filters.plan !== "all") params.set("plan", filters.plan);
    if (filters.status !== "all") params.set("subscription_status", filters.status);

    setLoading(true);
    setMessage("");
    try {
      const response = await adminApiFetch(`/admin/subscriptions?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminSubscription> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "구독 현황을 불러오지 못했습니다."));
      }
      setSubscriptions(data.items);
      setTotal(data.total);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "구독 현황을 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadSubscriptions(appliedFilters);
  }, [admin, appliedFilters, loadSubscriptions, ready]);

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters({ search, plan, status });
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">SUBSCRIPTIONS</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">구독 현황</h1>
            <p className="mt-2 text-sm text-white/50">회원의 플랜, 이용 기간, 해지 예정 상태를 확인합니다.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadSubscriptions(appliedFilters)}
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
              <CreditCard size={19} className="text-[#a78bfa]" />
            </div>
            <strong className="mt-6 block text-3xl font-extrabold tabular-nums">{total.toLocaleString("ko-KR")}건</strong>
          </section>
          <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-semibold text-white/60">표시된 해지 예정</p>
              <TimerReset size={19} className="text-[#a78bfa]" />
            </div>
            <strong className="mt-6 block text-3xl font-extrabold tabular-nums">{scheduledCancellationCount.toLocaleString("ko-KR")}건</strong>
          </section>
        </div>

        <form onSubmit={handleFilterSubmit} className="mt-7 grid gap-3 rounded-2xl border border-white/10 bg-[#102039]/90 p-4 lg:grid-cols-[minmax(0,1fr)_9rem_10rem_auto]">
          <label className="relative block">
            <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="아이디 또는 이메일 검색"
              className="h-11 w-full border border-white/15 bg-[#0b1729] pl-10 pr-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
            />
          </label>
          <select
            value={plan}
            onChange={(event) => setPlan(event.target.value as PlanFilter)}
            className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
          >
            <option value="all">전체 플랜</option>
            <option value="premium">프리미엄</option>
            <option value="free">무료</option>
          </select>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
          >
            <option value="all">전체 상태</option>
            <option value="active">이용 중</option>
            <option value="inactive">비활성</option>
            <option value="canceled">해지됨</option>
            <option value="expired">만료됨</option>
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
          <p role="alert" className="mt-5 border border-[#f87171]/35 bg-[#f87171]/10 px-4 py-3 text-sm text-[#fecaca]">
            {message}
          </p>
        )}

        <div className="mt-7 overflow-hidden rounded-2xl border border-white/10 bg-[#102039]/90">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div className="flex items-center gap-2">
              <CreditCard size={18} className="text-[#a78bfa]" />
              <h2 className="text-sm font-bold">구독 목록</h2>
            </div>
            <span className="text-sm text-white/50">최근 100건까지 표시</span>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-[960px] w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-[#0b1729]/70 text-xs text-white/45">
                <tr>
                  <th className="px-5 py-3 font-semibold">회원</th>
                  <th className="px-5 py-3 font-semibold">플랜</th>
                  <th className="px-5 py-3 font-semibold">구독 상태</th>
                  <th className="px-5 py-3 font-semibold">이용 기간</th>
                  <th className="px-5 py-3 font-semibold">결제 제공자</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {loading && subscriptions.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-white/45">구독 현황을 불러오고 있습니다.</td>
                  </tr>
                ) : subscriptions.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-white/45">조건에 맞는 구독 정보가 없습니다.</td>
                  </tr>
                ) : (
                  subscriptions.map((subscription) => (
                    <tr key={subscription.id} className="transition hover:bg-white/[0.025]">
                      <td className="px-5 py-4">
                        <p className="font-bold text-white">{subscription.username}</p>
                        <p className="mt-1 text-xs text-white/45">{subscription.email}</p>
                      </td>
                      <td className="px-5 py-4">
                        <span className={`inline-flex border px-2.5 py-1 text-xs font-bold ${
                          subscription.plan === "premium"
                            ? "border-[#a78bfa]/35 bg-[#8b5cf6]/10 text-[#ddd6fe]"
                            : "border-white/15 bg-white/5 text-white/65"
                        }`}>
                          {subscription.plan === "premium" ? "프리미엄" : "무료"}
                        </span>
                      </td>
                      <td className="px-5 py-4">
                        <span className={`inline-flex border px-2.5 py-1 text-xs font-bold ${statusClass(subscription.status)}`}>
                          {STATUS_LABELS[subscription.status] || subscription.status}
                        </span>
                        {subscription.cancel_at_period_end && (
                          <p className="mt-1.5 text-xs text-[#fde68a]">기간 종료 시 해지</p>
                        )}
                      </td>
                      <td className="px-5 py-4 text-white/65">
                        <p>{formatDate(subscription.current_period_start)} ~ {formatDate(subscription.current_period_end)}</p>
                        {subscription.cancel_requested_at && (
                          <p className="mt-1 text-xs text-white/40">해지 요청: {formatDate(subscription.cancel_requested_at)}</p>
                        )}
                      </td>
                      <td className="px-5 py-4 text-white/55">{subscription.provider || "-"}</td>
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
