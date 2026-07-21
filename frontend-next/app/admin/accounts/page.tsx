"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, ShieldCheck, UserCog, UserRoundCheck, UserRoundX } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import {
  type AdminAccount,
  type AdminListResponse,
  type AdminManagedUser,
  type AdminRole,
  adminApiFetch,
} from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function roleLabel(role: AdminRole): string {
  return role === "super_admin" ? "최고 관리자" : "운영자";
}

export default function AdminAccountsPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [accounts, setAccounts] = useState<AdminAccount[]>([]);
  const [total, setTotal] = useState(0);
  const [accountSearch, setAccountSearch] = useState("");
  const [appliedAccountSearch, setAppliedAccountSearch] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [candidates, setCandidates] = useState<AdminManagedUser[]>([]);
  const [selectedMember, setSelectedMember] = useState<AdminManagedUser | null>(null);
  const [newRole, setNewRole] = useState<AdminRole>("operator");
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  const canManageAccounts = admin?.role === "super_admin";

  const loadAccounts = useCallback(async (search: string) => {
    const params = new URLSearchParams({ limit: "100" });
    if (search.trim()) params.set("search", search.trim());

    setLoadingAccounts(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/accounts?${params.toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminAccount> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "관리자 계정 목록을 불러오지 못했습니다."));
      }
      setAccounts(data.items);
      setTotal(data.total);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "관리자 계정 목록을 불러오지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoadingAccounts(false);
    }
  }, []);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (ready && canManageAccounts) void loadAccounts(appliedAccountSearch);
  }, [appliedAccountSearch, canManageAccounts, loadAccounts, ready]);

  function handleAccountSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedAccountSearch(accountSearch);
  }

  async function searchMembers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const keyword = memberSearch.trim();
    if (!keyword) {
      setCandidates([]);
      setSelectedMember(null);
      return;
    }

    setLoadingCandidates(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/users?${new URLSearchParams({ limit: "10", search: keyword }).toString()}`);
      const data = (await readJsonSafely(response)) as AdminListResponse<AdminManagedUser> | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "회원을 찾지 못했습니다."));
      }
      setCandidates(data.items);
      setSelectedMember(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "회원을 찾지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoadingCandidates(false);
    }
  }

  async function createAccount() {
    if (!selectedMember) {
      setMessage("관리자로 지정할 회원을 먼저 선택해 주세요.");
      setMessageKind("error");
      return;
    }
    if (!window.confirm(`${selectedMember.username}님을 ${roleLabel(newRole)}로 지정할까요?`)) return;

    setProcessingId(selectedMember.id);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch("/admin/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: selectedMember.id, role: newRole }),
      });
      const data = (await readJsonSafely(response)) as AdminAccount | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "관리자 계정을 지정하지 못했습니다."));
      }
      setAccounts((current) => [data, ...current]);
      setTotal((current) => current + 1);
      setCandidates([]);
      setSelectedMember(null);
      setMemberSearch("");
      setMessage(`${data.username}님을 ${roleLabel(data.role)}로 지정했습니다.`);
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "관리자 계정을 지정하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setProcessingId(null);
    }
  }

  async function updateAccount(
    account: AdminAccount,
    path: "role" | "status",
    body: { role: AdminRole } | { is_active: boolean },
    successMessage: string
  ) {
    setProcessingId(account.id);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch(`/admin/accounts/${account.id}/${path}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await readJsonSafely(response)) as AdminAccount | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "관리자 계정을 변경하지 못했습니다."));
      }
      setAccounts((current) => current.map((item) => (item.id === data.id ? data : item)));
      setMessage(successMessage);
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "관리자 계정을 변경하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setProcessingId(null);
    }
  }

  function changeRole(account: AdminAccount, role: AdminRole) {
    if (role === account.role) return;
    if (!window.confirm(`${account.username}님의 권한을 ${roleLabel(role)}로 변경할까요?`)) return;
    void updateAccount(account, "role", { role }, `${account.username}님의 권한을 변경했습니다.`);
  }

  function toggleStatus(account: AdminAccount) {
    const nextActive = !account.is_active;
    const action = nextActive ? "활성화" : "비활성화";
    if (!window.confirm(`${account.username}님의 관리자 계정을 ${action}할까요?`)) return;
    void updateAccount(account, "status", { is_active: nextActive }, `${account.username}님의 관리자 계정을 ${action}했습니다.`);
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div>
          <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">ACCESS CONTROL</p>
          <h1 className="mt-2 text-3xl font-extrabold tracking-normal">관리자 계정</h1>
          <p className="mt-2 text-sm text-white/50">관리자 권한과 계정 상태를 관리합니다.</p>
        </div>

        {!canManageAccounts ? (
          <section className="mt-7 rounded-2xl border border-[#a78bfa]/30 bg-[#8b5cf6]/10 px-5 py-6 text-sm leading-6 text-[#ddd6fe]">
            관리자 계정 관리 기능은 최고 관리자만 사용할 수 있습니다.
          </section>
        ) : (
          <>
            <div className="mt-7 grid gap-3 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
              <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
                <div className="flex items-center gap-2">
                  <ShieldCheck size={18} className="text-[#a78bfa]" />
                  <h2 className="text-sm font-bold">관리자 지정</h2>
                </div>
                <form onSubmit={searchMembers} className="mt-5 flex gap-2">
                  <input
                    type="search"
                    value={memberSearch}
                    onChange={(event) => setMemberSearch(event.target.value)}
                    placeholder="아이디 또는 이메일로 회원 찾기"
                    className="h-10 min-w-0 flex-1 rounded-xl border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
                  />
                  <button
                    type="submit"
                    disabled={loadingCandidates}
                    className="inline-flex h-10 items-center gap-1.5 rounded-xl border border-[#a78bfa]/50 px-3 text-sm font-bold text-[#ddd6fe] transition hover:bg-[#8b5cf6]/15 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <Search size={16} />
                    찾기
                  </button>
                </form>

                <div className="mt-3 max-h-40 divide-y divide-white/10 overflow-y-auto rounded-xl border border-white/10">
                  {loadingCandidates ? (
                    <p className="px-3 py-4 text-sm text-white/45">회원을 찾고 있습니다.</p>
                  ) : candidates.length === 0 ? (
                    <p className="px-3 py-4 text-sm text-white/45">검색한 회원이 여기에 표시됩니다.</p>
                  ) : (
                    candidates.map((member) => (
                      <button
                        key={member.id}
                        type="button"
                        onClick={() => setSelectedMember(member)}
                        className={`w-full px-3 py-3 text-left text-sm transition hover:bg-white/[0.025] ${
                          selectedMember?.id === member.id ? "bg-[#8b5cf6]/10" : ""
                        }`}
                      >
                        <span className="block font-bold text-white">{member.username}</span>
                        <span className="mt-1 block text-xs text-white/45">{member.email}{member.is_active ? "" : " · 비활성 회원"}</span>
                      </button>
                    ))
                  )}
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
                  <select
                    value={newRole}
                    onChange={(event) => setNewRole(event.target.value as AdminRole)}
                    className="h-10 rounded-xl border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none focus:border-[#a78bfa]"
                  >
                    <option value="operator">운영자</option>
                    <option value="super_admin">최고 관리자</option>
                  </select>
                  <button
                    type="button"
                    onClick={createAccount}
                    disabled={!selectedMember || processingId !== null}
                    className="h-10 rounded-xl bg-[#8b5cf6] px-4 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    관리자 지정
                  </button>
                </div>
              </section>

              <section className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <UserCog size={18} className="text-[#a78bfa]" />
                      <h2 className="text-sm font-bold">등록된 관리자</h2>
                    </div>
                    <p className="mt-3 text-3xl font-extrabold tabular-nums">{total.toLocaleString("ko-KR")}명</p>
                  </div>
                  <form onSubmit={handleAccountSearch} className="flex w-full max-w-64 gap-2">
                    <input
                      type="search"
                      value={accountSearch}
                      onChange={(event) => setAccountSearch(event.target.value)}
                      placeholder="관리자 검색"
                      className="h-10 min-w-0 flex-1 rounded-xl border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
                    />
                    <button type="submit" className="grid size-10 place-items-center rounded-xl border border-white/15 text-white/70 transition hover:border-[#a78bfa]/60 hover:text-white" aria-label="관리자 검색" title="관리자 검색">
                      <Search size={16} />
                    </button>
                  </form>
                </div>
              </section>
            </div>

            {message && (
              <p
                role={messageKind === "error" ? "alert" : "status"}
                className={`mt-5 rounded-xl border px-4 py-3 text-sm ${
                  messageKind === "error"
                    ? "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]"
                    : "border-[#a78bfa]/30 bg-[#8b5cf6]/10 text-[#ddd6fe]"
                }`}
              >
                {message}
              </p>
            )}

            <section className="mt-7 overflow-hidden rounded-2xl border border-white/10 bg-[#102039]/90">
              <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
                <h2 className="text-sm font-bold">관리자 목록</h2>
                <span className="text-sm text-white/50">최근 100명까지 표시</span>
              </div>
              <div className="overflow-x-auto">
                <table className="min-w-[860px] w-full text-left text-sm">
                  <thead className="border-b border-white/10 bg-[#0b1729]/70 text-xs text-white/45">
                    <tr>
                      <th className="px-5 py-3 font-semibold">관리자</th>
                      <th className="px-5 py-3 font-semibold">권한</th>
                      <th className="px-5 py-3 font-semibold">계정 상태</th>
                      <th className="px-5 py-3 font-semibold">지정일</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/10">
                    {loadingAccounts && accounts.length === 0 ? (
                      <tr><td colSpan={4} className="px-5 py-14 text-center text-white/45">관리자 계정을 불러오고 있습니다.</td></tr>
                    ) : accounts.length === 0 ? (
                      <tr><td colSpan={4} className="px-5 py-14 text-center text-white/45">등록된 관리자 계정이 없습니다.</td></tr>
                    ) : (
                      accounts.map((account) => {
                        const isCurrentAdmin = account.user_id === admin.id;
                        const processing = processingId === account.id;
                        return (
                          <tr key={account.id} className="transition hover:bg-white/[0.025]">
                            <td className="px-5 py-4">
                              <p className="font-bold text-white">{account.username}{isCurrentAdmin ? " (나)" : ""}</p>
                              <p className="mt-1 text-xs text-white/45">{account.email}</p>
                            </td>
                            <td className="px-5 py-4">
                              <select
                                value={account.role}
                                disabled={isCurrentAdmin || processing}
                                onChange={(event) => changeRole(account, event.target.value as AdminRole)}
                                className="h-9 min-w-28 border border-white/15 bg-[#0b1729] px-3 text-sm font-semibold text-white outline-none focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                <option value="operator">운영자</option>
                                <option value="super_admin">최고 관리자</option>
                              </select>
                            </td>
                            <td className="px-5 py-4">
                              <button
                                type="button"
                                disabled={isCurrentAdmin || processing}
                                onClick={() => toggleStatus(account)}
                                className={`inline-flex h-9 items-center gap-2 border px-3 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-50 ${
                                  account.is_active
                                    ? "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd] hover:bg-[#5be3a0]/20"
                                    : "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca] hover:bg-[#f87171]/20"
                                }`}
                              >
                                {account.is_active ? <UserRoundCheck size={16} /> : <UserRoundX size={16} />}
                                {account.is_active ? "활성" : "비활성"}
                              </button>
                            </td>
                            <td className="px-5 py-4 text-white/55">{formatDate(account.created_at)}</td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </section>
    </AdminShell>
  );
}
