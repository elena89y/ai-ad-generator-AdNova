"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BadgeDollarSign,
  ImageIcon,
  RefreshCw,
  UsersRound,
  MessageSquareMore,
} from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import { type AdminSummary, adminApiFetch } from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

const summaryCards = [
  { key: "total_users", label: "전체 회원", icon: UsersRound, suffix: "명" },
  { key: "premium_users", label: "프리미엄 회원", icon: BadgeDollarSign, suffix: "명" },
  { key: "total_advertisements", label: "생성 광고", icon: ImageIcon, suffix: "건" },
  { key: "unresolved_inquiries", label: "답변 대기 문의", icon: MessageSquareMore, suffix: "건" },
] as const;

function formatAmount(amount: number): string {
  return new Intl.NumberFormat("ko-KR", {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(amount);
}

export default function AdminDashboardPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const loadSummary = useCallback(async () => {
    setLoading(true);
    setMessage("");
    try {
      const response = await adminApiFetch("/admin/summary");
      const data = (await readJsonSafely(response)) as AdminSummary | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "관리자 대시보드를 불러오지 못했습니다."));
      }
      setSummary(data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "관리자 대시보드를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadSummary();
  }, [admin, loadSummary, ready]);

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">OVERVIEW</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">대시보드</h1>
            <p className="mt-2 text-sm text-white/50">서비스 운영 현황을 확인합니다.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadSummary()}
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-white/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        {message && (
          <div role="alert" className="mt-7 border border-[#ed6a5e]/35 bg-[#ed6a5e]/10 px-4 py-3 text-sm text-[#ffb0a8]">
            {message}
          </div>
        )}

        <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {summaryCards.map(({ key, label, icon: Icon, suffix }) => (
            <article key={key} className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
              <div className="flex items-start justify-between gap-4">
                <span className="text-sm font-semibold text-white/60">{label}</span>
                <Icon size={19} className="text-[#a78bfa]" />
              </div>
              <strong className="mt-7 block text-3xl font-extrabold tabular-nums">
                {summary ? `${summary[key].toLocaleString("ko-KR")}${suffix}` : "-"}
              </strong>
            </article>
          ))}
        </div>

        <div className="mt-8 grid gap-3 lg:grid-cols-2">
          <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
            <p className="text-sm font-semibold text-white/60">이번 달 결제액</p>
            <strong className="mt-4 block text-3xl font-extrabold tabular-nums">
              {summary ? formatAmount(summary.monthly_paid_purchase_amount) : "-"}
            </strong>
            <p className="mt-3 text-sm text-white/45">
              완료된 결제 {summary?.paid_purchase_count.toLocaleString("ko-KR") ?? "-"}건 기준
            </p>
          </section>
          <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
            <p className="text-sm font-semibold text-white/60">관리자 권한</p>
            <strong className="mt-4 block text-2xl font-extrabold">
              {admin.role === "super_admin" ? "최고 관리자" : "운영자"}
            </strong>
            <p className="mt-3 text-sm text-white/45">{admin.email}</p>
          </section>
        </div>
      </section>
    </AdminShell>
  );
}
