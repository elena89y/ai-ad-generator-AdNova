"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RefreshCw, Search, UserRoundCheck, UserRoundX, UsersRound, X } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminListResponse,
  type AdminManagedUser,
  type AdminUserDetail,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

type PlanFilter = "all" | "free" | "premium";
type StatusFilter = "all" | "active" | "inactive";
type UserFilters = {
  search: string;
  plan: PlanFilter;
  status: StatusFilter;
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function getDisplayName(user: AdminManagedUser): string {
  return user.name || user.business_name || user.username;
}

export default function AdminUsersPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [users, setUsers] = useState<AdminManagedUser[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [plan, setPlan] = useState<PlanFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [appliedFilters, setAppliedFilters] = useState<UserFilters>({
    search: "",
    plan: "all",
    status: "all",
  });
  const [loading, setLoading] = useState(false);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);
  const [detailTarget, setDetailTarget] = useState<AdminManagedUser | null>(null);
  const [detailUser, setDetailUser] = useState<AdminUserDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadUsers = useCallback(async (filters: UserFilters) => {
    const params = new URLSearchParams({ limit: "100" });
    const keyword = filters.search.trim();
    if (keyword) params.set("search", keyword);
    if (filters.plan !== "all") params.set("plan", filters.plan);
    if (filters.status !== "all") params.set("is_active", String(filters.status === "active"));

    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/users?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminManagedUser> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "회원 목록을 불러오지 못했습니다."));
      }
      setUsers(data.items);
      setTotal(data.total);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "회원 목록을 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && admin) void loadUsers(appliedFilters);
  }, [admin, appliedFilters, loadUsers, ready]);

  async function updateUser(
    user: AdminManagedUser,
    path: "status" | "subscription",
    body: { is_active: boolean } | { is_premium: boolean },
    successMessage: string
  ) {
    setProcessingId(user.id);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/users/${user.id}/${path}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await readJsonSafely(response)) as AdminManagedUser | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "회원 정보를 변경하지 못했습니다."));
      }

      setUsers((current) => current.map((item) => (item.id === data.id ? data : item)));
      setDetailUser((current) => (current?.id === data.id ? { ...current, ...data } : current));
      setMessage(successMessage);
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "회원 정보를 변경하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setProcessingId(null);
    }
  }

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters({ search, plan, status });
  }

  function changePlan(user: AdminManagedUser, nextPlan: "free" | "premium") {
    if (nextPlan === user.plan) return;
    const label = nextPlan === "premium" ? "프리미엄" : "무료";
    if (!window.confirm(`${user.username}님의 플랜을 ${label}로 변경할까요?`)) return;
    void updateUser(
      user,
      "subscription",
      { is_premium: nextPlan === "premium" },
      `${user.username}님의 플랜을 ${label}로 변경했습니다.`
    );
  }

  function toggleStatus(user: AdminManagedUser) {
    const nextActive = !user.is_active;
    const action = nextActive ? "활성화" : "비활성화";
    const notice = nextActive ? "" : " 로그인과 서비스 이용이 제한됩니다.";
    if (!window.confirm(`${user.username}님 계정을 ${action}할까요?${notice}`)) return;
    void updateUser(
      user,
      "status",
      { is_active: nextActive },
      `${user.username}님 계정을 ${action}했습니다.`
    );
  }

  async function openUserDetail(user: AdminManagedUser) {
    setDetailTarget(user);
    setDetailUser(null);
    setDetailLoading(true);
    try {
      const response = await adminApiFetch(`/admin/users/${user.id}`);
      const data = (await readJsonSafely(response)) as AdminUserDetail | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "회원 상세 정보를 불러오지 못했습니다."));
      }
      setDetailUser(data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "회원 상세 정보를 불러오지 못했습니다.");
      setMessageKind("error");
      setDetailTarget(null);
    } finally {
      setDetailLoading(false);
    }
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  const canManageUsers = admin.role === "super_admin";

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">MEMBERS</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">회원 관리</h1>
            <p className="mt-2 text-sm text-white/50">회원 계정 상태와 구독 플랜을 관리합니다.</p>
          </div>
          <button
            type="button"
            onClick={() => void loadUsers(appliedFilters)}
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/15 px-4 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            새로고침
          </button>
        </div>

        {!canManageUsers && (
          <p className="mt-6 border border-[#a78bfa]/30 bg-[#8b5cf6]/10 px-4 py-3 text-sm text-[#ddd6fe]">
            운영자는 회원 정보를 조회할 수 있습니다. 플랜과 계정 상태 변경은 최고 관리자만 할 수 있습니다.
          </p>
        )}

        <form onSubmit={handleFilterSubmit} className="mt-7 grid gap-3 border border-white/10 bg-[#102039]/90 p-4 lg:grid-cols-[minmax(0,1fr)_10rem_10rem_auto]">
          <label className="relative block">
            <Search size={17} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="아이디, 이메일, 이름, 사업자명 검색"
              className="h-11 w-full border border-white/15 bg-[#0b1729] pl-10 pr-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
            />
          </label>
          <select
            value={plan}
            onChange={(event) => setPlan(event.target.value as PlanFilter)}
            className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
          >
            <option value="all">전체 플랜</option>
            <option value="free">무료</option>
            <option value="premium">프리미엄</option>
          </select>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as StatusFilter)}
            className="h-11 border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
          >
            <option value="all">전체 상태</option>
            <option value="active">활성</option>
            <option value="inactive">비활성</option>
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

        <div className="mt-7 overflow-hidden border border-white/10 bg-[#102039]/90">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div className="flex items-center gap-2">
              <UsersRound size={18} className="text-[#a78bfa]" />
              <h2 className="text-sm font-bold">회원 목록</h2>
            </div>
            <span className="text-sm text-white/50">총 {total.toLocaleString("ko-KR")}명</span>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-[960px] w-full text-left text-sm">
              <thead className="border-b border-white/10 bg-[#0b1729]/70 text-xs text-white/45">
                <tr>
                  <th className="px-5 py-3 font-semibold">회원</th>
                  <th className="px-5 py-3 font-semibold">플랜</th>
                  <th className="px-5 py-3 font-semibold">계정 상태</th>
                  <th className="px-5 py-3 font-semibold">가입일</th>
                  <th className="px-5 py-3 font-semibold">상세</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {loading && users.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-white/45">회원 목록을 불러오고 있습니다.</td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-5 py-14 text-center text-white/45">조건에 맞는 회원이 없습니다.</td>
                  </tr>
                ) : (
                  users.map((user) => {
                    const processing = processingId === user.id;
                    return (
                      <tr key={user.id} className="transition hover:bg-white/[0.025]">
                        <td className="px-5 py-4">
                          <p className="font-bold text-white">{getDisplayName(user)}</p>
                          <p className="mt-1 text-xs text-white/45">{user.username} · {user.email}</p>
                        </td>
                        <td className="px-5 py-4">
                          <select
                            value={user.plan}
                            disabled={!canManageUsers || processing}
                            onChange={(event) => changePlan(user, event.target.value as "free" | "premium")}
                            className="h-9 min-w-28 border border-white/15 bg-[#0b1729] px-3 text-sm font-semibold text-white outline-none focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <option value="free">무료</option>
                            <option value="premium">프리미엄</option>
                          </select>
                          {user.subscription_status && (
                            <p className="mt-1.5 text-xs text-white/40">{user.subscription_status}</p>
                          )}
                        </td>
                        <td className="px-5 py-4">
                          <button
                            type="button"
                            disabled={!canManageUsers || processing}
                            onClick={() => toggleStatus(user)}
                            className={`inline-flex h-9 items-center gap-2 border px-3 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                              user.is_active
                                ? "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd] hover:bg-[#5be3a0]/20"
                                : "border-[#f87171]/35 bg-[#f87171]/10 text-[#fca5a5] hover:bg-[#f87171]/20"
                            }`}
                          >
                            {user.is_active ? <UserRoundCheck size={16} /> : <UserRoundX size={16} />}
                            {user.is_active ? "활성" : "비활성"}
                          </button>
                        </td>
                        <td className="px-5 py-4 text-white/55">{formatDate(user.created_at)}</td>
                        <td className="px-5 py-4">
                          <button
                            type="button"
                            onClick={() => void openUserDetail(user)}
                            className="h-9 border border-white/15 px-3 text-sm font-bold text-white/75 transition hover:border-[#a78bfa]/60 hover:text-white"
                          >
                            상세 보기
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {detailTarget && (
          <div className="fixed inset-0 z-50 grid place-items-center bg-[#020617]/80 px-5 py-8" role="dialog" aria-modal="true" aria-labelledby="user-detail-title">
            <section className="w-full max-w-xl border border-white/15 bg-[#102039] p-6 shadow-2xl shadow-black/40">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold tracking-[0.14em] text-[#a78bfa]">MEMBER DETAIL</p>
                  <h2 id="user-detail-title" className="mt-2 text-xl font-extrabold">회원 상세</h2>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setDetailTarget(null);
                    setDetailUser(null);
                  }}
                  className="grid size-9 place-items-center text-white/55 transition hover:bg-white/5 hover:text-white"
                  aria-label="회원 상세 창 닫기"
                  title="닫기"
                >
                  <X size={19} />
                </button>
              </div>

              {detailLoading || !detailUser ? (
                <p className="py-12 text-center text-sm text-white/50">회원 상세 정보를 불러오고 있습니다.</p>
              ) : (
                <dl className="mt-6 grid gap-y-3 text-sm sm:grid-cols-[8rem_minmax(0,1fr)]">
                  <dt className="text-white/45">회원 ID</dt>
                  <dd className="font-semibold text-white">{detailUser.id}</dd>
                  <dt className="text-white/45">아이디</dt>
                  <dd className="text-white/80">{detailUser.username}</dd>
                  <dt className="text-white/45">이메일</dt>
                  <dd className="break-all text-white/80">{detailUser.email}</dd>
                  <dt className="text-white/45">이름 / 사업자명</dt>
                  <dd className="text-white/80">{detailUser.name || detailUser.business_name || "-"}</dd>
                  <dt className="text-white/45">업종</dt>
                  <dd className="text-white/80">{detailUser.business_type || "-"}</dd>
                  <dt className="text-white/45">플랜 / 구독 상태</dt>
                  <dd className="text-white/80">{detailUser.plan === "premium" ? "프리미엄" : "무료"} · {detailUser.subscription_status || "-"}</dd>
                  <dt className="text-white/45">계정 상태</dt>
                  <dd className={detailUser.is_active ? "text-[#8af0bd]" : "text-[#fca5a5]"}>{detailUser.is_active ? "활성" : "비활성"}</dd>
                  <dt className="text-white/45">광고 생성 수</dt>
                  <dd className="font-semibold text-white">{detailUser.advertisement_count.toLocaleString("ko-KR")}건</dd>
                  <dt className="text-white/45">가입일</dt>
                  <dd className="text-white/80">{formatDate(detailUser.created_at)}</dd>
                  <dt className="text-white/45">마지막 수정</dt>
                  <dd className="text-white/80">{formatDate(detailUser.updated_at)}</dd>
                </dl>
              )}
            </section>
          </div>
        )}
      </section>
    </AdminShell>
  );
}
