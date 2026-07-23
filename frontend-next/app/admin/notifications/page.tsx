"use client";

import { type FormEvent, useEffect, useState } from "react";
import { Crown, MailCheck, MailPlus, ShieldCheck, UsersRound, X } from "lucide-react";
import { useRouter } from "next/navigation";

import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import { adminApiFetch, type AdminManagedUser, type AdminListResponse } from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

interface MarketingResult {
  eligible_count: number;
  sent_count: number;
  failed_count: number;
}

type MarketingAudience = "all" | "premium" | "free" | "selected";

function audienceCardClass(active: boolean): string {
  return active
    ? "cursor-pointer rounded-xl border border-[#a78bfa]/60 bg-[#8b5cf6]/15 px-4 py-3 transition"
    : "cursor-pointer rounded-xl border border-white/10 bg-[#0b1729] px-4 py-3 transition hover:border-white/25";
}

export default function AdminNotificationsPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [audience, setAudience] = useState<MarketingAudience>("all");
  const [memberSearch, setMemberSearch] = useState("");
  const [memberResults, setMemberResults] = useState<AdminManagedUser[]>([]);
  const [selectedMembers, setSelectedMembers] = useState<AdminManagedUser[]>([]);
  const [searchingMembers, setSearchingMembers] = useState(false);
  const [result, setResult] = useState<MarketingResult | null>(null);
  const [notice, setNotice] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  useEffect(() => {
    if (audience !== "selected") {
      setMemberResults([]);
      return;
    }

    const keyword = memberSearch.trim();
    if (!keyword) {
      setMemberResults([]);
      return;
    }

    const timer = window.setTimeout(async () => {
      setSearchingMembers(true);
      try {
        const params = new URLSearchParams({ search: keyword, limit: "20" });
        const response = await adminApiFetch(`/admin/users?${params.toString()}`);
        const data = (await readJsonSafely(response)) as AdminListResponse<AdminManagedUser> | null;
        if (response.ok && data) setMemberResults(data.items);
        else setMemberResults([]);
      } finally {
        setSearchingMembers(false);
      }
    }, 250);

    return () => window.clearTimeout(timer);
  }, [admin, audience, memberSearch]);

  function toggleMember(member: AdminManagedUser): void {
    setSelectedMembers((current) =>
      current.some((selected) => selected.id === member.id)
        ? current.filter((selected) => selected.id !== member.id)
        : [...current, member],
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    setResult(null);

    const trimmedSubject = subject.trim();
    const trimmedMessage = message.trim();
    if (!trimmedSubject || !trimmedMessage) {
      setNotice("메일 제목과 내용을 모두 입력해 주세요.");
      return;
    }

    let selectedUserIds: number[] | undefined;
    if (audience === "selected") {
      if (selectedMembers.length === 0) {
        setNotice("발송할 회원을 하나 이상 선택해 주세요.");
        return;
      }
      selectedUserIds = selectedMembers.map((member) => member.id);
    }

    if (!window.confirm("선택한 대상에게 마케팅 메일을 발송할까요?")) return;

    setSending(true);
    try {
      const response = await adminApiFetch("/admin/notifications/marketing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          subject: trimmedSubject,
          message: trimmedMessage,
          audience,
          ...(selectedUserIds ? { user_ids: selectedUserIds } : {}),
        }),
      });
      const data = (await readJsonSafely(response)) as MarketingResult | null;
      if (!response.ok || !data) {
        throw new Error(readApiError(data, "마케팅 메일을 발송하지 못했습니다."));
      }
      setResult(data);
      setNotice("메일 발송이 완료되었습니다.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "마케팅 메일을 발송하지 못했습니다.");
    } finally {
      setSending(false);
    }
  }

  if (!ready || !admin) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">
        관리자 인증을 확인하고 있습니다.
      </main>
    );
  }

  const isSuperAdmin = admin.role === "super_admin";

  return (
    <AdminShell>
      <section className="px-5 py-8 lg:px-9 lg:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">MARKETING</p>
            <h1 className="mt-2 text-3xl font-extrabold tracking-normal">마케팅 알림</h1>
            <p className="mt-2 text-sm text-white/50">
              수신에 동의한 회원에게 새로운 소식과 혜택을 전달합니다.
            </p>
          </div>
          <div className="inline-flex items-center gap-2 rounded-xl border border-[#a78bfa]/30 bg-[#8b5cf6]/10 px-3 py-2 text-xs font-bold text-[#ddd6fe]">
            <ShieldCheck size={16} /> 최고 관리자 전용
          </div>
        </div>

        {!isSuperAdmin ? (
          <div className="mt-8 rounded-2xl border border-[#f87171]/35 bg-[#f87171]/10 px-5 py-4 text-sm text-[#fecaca]">
            마케팅 메일 발송은 최고 관리자만 사용할 수 있습니다.
          </div>
        ) : (
          <div className="mt-8 grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)]">
            <form
              onSubmit={handleSubmit}
              className="rounded-2xl border border-white/10 bg-[#102039]/90 p-5 sm:p-6"
            >
              <div className="flex items-center gap-2">
                <MailPlus size={19} className="text-[#a78bfa]" />
                <h2 className="text-sm font-bold">새 알림 작성</h2>
              </div>
              <p className="mt-2 text-xs leading-5 text-white/45">
                광고성 소식 수신에 동의한 회원에게만 발송됩니다.
              </p>

              <div className="mt-6 grid gap-4">
                <label className="grid gap-1.5 text-xs font-semibold text-white/55">
                  메일 제목
                  <input
                    value={subject}
                    onChange={(event) => setSubject(event.target.value)}
                    maxLength={120}
                    placeholder="새로운 템플릿이 도착했어요"
                    className="h-11 rounded-xl border border-white/15 bg-[#0b1729] px-3 text-sm font-normal text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
                  />
                </label>
                <label className="grid gap-1.5 text-xs font-semibold text-white/55">
                  메일 내용
                  <textarea
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    maxLength={5000}
                    rows={9}
                    placeholder="회원에게 전달할 내용을 입력해 주세요."
                    className="resize-y rounded-xl border border-white/15 bg-[#0b1729] px-3 py-3 text-sm font-normal leading-6 text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
                  />
                  <span className="text-right text-[11px] font-normal text-white/35">
                    {message.length.toLocaleString("ko-KR")} / 5,000
                  </span>
                </label>
              </div>

              <fieldset className="mt-5">
                <legend className="text-xs font-semibold text-white/55">발송 대상</legend>
                <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                  <label className={audienceCardClass(audience === "all")}>
                    <input
                      type="radio"
                      name="audience"
                      value="all"
                      checked={audience === "all"}
                      onChange={() => setAudience("all")}
                      className="sr-only"
                    />
                    <span className="flex items-center gap-2 text-sm font-bold text-white">
                      <UsersRound size={16} className="text-[#a78bfa]" /> 수신 동의 전체
                    </span>
                  </label>
                  <label className={audienceCardClass(audience === "premium")}>
                    <input
                      type="radio"
                      name="audience"
                      value="premium"
                      checked={audience === "premium"}
                      onChange={() => setAudience("premium")}
                      className="sr-only"
                    />
                    <span className="flex items-center gap-2 text-sm font-bold text-white">
                      <Crown size={16} className="text-[#fbbf24]" /> 프리미엄 회원
                    </span>
                    <span className="mt-1 block text-xs text-white/40">수신 동의 프리미엄 회원</span>
                  </label>
                  <label className={audienceCardClass(audience === "free")}>
                    <input
                      type="radio"
                      name="audience"
                      value="free"
                      checked={audience === "free"}
                      onChange={() => setAudience("free")}
                      className="sr-only"
                    />
                    <span className="flex items-center gap-2 text-sm font-bold text-white">
                      <UsersRound size={16} className="text-[#60a5fa]" /> 무료 회원
                    </span>
                    <span className="mt-1 block text-xs text-white/40">수신 동의 무료 회원</span>
                  </label>
                  <label className={audienceCardClass(audience === "selected")}>
                    <input
                      type="radio"
                      name="audience"
                      value="selected"
                      checked={audience === "selected"}
                      onChange={() => setAudience("selected")}
                      className="sr-only"
                    />
                    <span className="flex items-center gap-2 text-sm font-bold text-white">
                      <MailCheck size={16} className="text-[#a78bfa]" /> 특정 회원만
                    </span>
                    <span className="mt-1 block text-xs text-white/40">닉네임으로 검색해 선택</span>
                  </label>
                </div>
                {audience === "selected" && (
                  <div className="mt-3 space-y-3">
                    <input
                      value={memberSearch}
                      onChange={(event) => setMemberSearch(event.target.value)}
                      placeholder="회원 닉네임 검색"
                      className="h-11 w-full rounded-xl border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
                    />
                    {selectedMembers.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {selectedMembers.map((member) => (
                          <button
                            key={member.id}
                            type="button"
                            onClick={() => toggleMember(member)}
                            className="inline-flex items-center gap-1 rounded-full border border-[#a78bfa]/40 bg-[#8b5cf6]/15 px-3 py-1 text-xs font-semibold text-[#ddd6fe]"
                          >
                            {member.username} <X size={13} />
                          </button>
                        ))}
                      </div>
                    )}
                    {(searchingMembers || memberResults.length > 0) && (
                      <div className="max-h-48 overflow-y-auto rounded-xl border border-white/10 bg-[#0b1729] p-1">
                        {searchingMembers ? (
                          <p className="px-3 py-2 text-xs text-white/45">회원 검색 중...</p>
                        ) : (
                          memberResults.map((member) => {
                            const selected = selectedMembers.some((item) => item.id === member.id);
                            return (
                              <button
                                key={member.id}
                                type="button"
                                onClick={() => toggleMember(member)}
                                className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-white transition hover:bg-white/10"
                              >
                                <span>
                                  <b>{member.username}</b>
                                  <span className="ml-2 text-xs text-white/40">{member.email}</span>
                                </span>
                                <span className="text-xs text-[#c4b5fd]">{selected ? "선택됨" : "선택"}</span>
                              </button>
                            );
                          })
                        )}
                      </div>
                    )}
                  </div>
                )}
              </fieldset>

              {notice && (
                <p
                  role="alert"
                  className={
                    result
                      ? "mt-5 border border-[#5be3a0]/35 bg-[#5be3a0]/10 px-4 py-3 text-sm text-[#8af0bd]"
                      : "mt-5 border border-[#fbbf24]/35 bg-[#fbbf24]/10 px-4 py-3 text-sm text-[#fde68a]"
                  }
                >
                  {notice}
                </p>
              )}

              {result && (
                <div className="mt-3 grid gap-2 text-xs text-white/60 sm:grid-cols-3">
                  <span>대상 {result.eligible_count.toLocaleString("ko-KR")}명</span>
                  <span className="text-[#8af0bd]">성공 {result.sent_count.toLocaleString("ko-KR")}명</span>
                  <span className="text-[#fca5a5]">실패 {result.failed_count.toLocaleString("ko-KR")}명</span>
                </div>
              )}

              <button
                type="submit"
                disabled={sending}
                className="mt-6 inline-flex h-11 items-center gap-2 rounded-xl bg-[#8b5cf6] px-5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <MailPlus size={17} />
                {sending ? "발송 중..." : "메일 발송하기"}
              </button>
            </form>

            <aside className="h-fit rounded-2xl border border-[#a78bfa]/25 bg-[#8b5cf6]/10 p-5 sm:p-6">
              <p className="text-xs font-bold tracking-[0.14em] text-[#c4b5fd]">CHECK BEFORE SEND</p>
              <h2 className="mt-3 text-xl font-extrabold">발송 전 확인</h2>
              <ul className="mt-5 space-y-4 text-sm leading-6 text-white/65">
                <li>• 수신 동의를 철회한 회원에게는 메일이 발송되지 않습니다.</li>
                <li>• 메일 본문은 일반 텍스트로 전달되며 줄바꿈이 유지됩니다.</li>
                <li>• 발송 결과와 실패 수는 감사 로그에 남습니다.</li>
                <li>• 실제 메일 발송이므로 제목과 내용을 확인한 뒤 진행해 주세요.</li>
              </ul>
            </aside>
          </div>
        )}
      </section>
    </AdminShell>
  );
}
