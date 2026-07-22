"use client";

import { type FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Copy, KeyRound, ShieldCheck, ShieldOff } from "lucide-react";

import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import { adminApiFetch } from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

type MessageResponse = { message?: string };
type TotpSetupResponse = {
  manual_entry_key?: string;
};

function onlyTotpDigits(value: string): string {
  return value.replace(/\D/g, "").slice(0, 6);
}

export default function AdminSecurityPage() {
  const router = useRouter();
  const { admin, ready, refreshAdmin } = useAdmin();
  const [currentPassword, setCurrentPassword] = useState("");
  const [setupCode, setSetupCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [manualEntryKey, setManualEntryKey] = useState("");
  const [loading, setLoading] = useState<"setup" | "confirm" | "disable" | null>(null);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  function showMessage(nextMessage: string, kind: "success" | "error") {
    setMessage(nextMessage);
    setMessageKind(kind);
  }

  async function handleSetup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentPassword) {
      showMessage("현재 비밀번호를 입력해 주세요.", "error");
      return;
    }

    setLoading("setup");
    setMessage("");
    try {
      const response = await adminApiFetch("/admin/totp/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword }),
      });
      const data = (await readJsonSafely(response)) as TotpSetupResponse | null;
      if (!response.ok || !data?.manual_entry_key) {
        throw new Error(readApiError(data, "2단계 인증 설정을 시작하지 못했습니다."));
      }
      setManualEntryKey(data.manual_entry_key);
      setSetupCode("");
      showMessage("인증 앱에 등록한 뒤 6자리 코드를 입력해 활성화해 주세요.", "success");
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "2단계 인증 설정을 시작하지 못했습니다.", "error");
    } finally {
      setLoading(null);
    }
  }

  async function handleConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!/^\d{6}$/.test(setupCode)) {
      showMessage("인증 앱의 6자리 코드를 입력해 주세요.", "error");
      return;
    }

    setLoading("confirm");
    setMessage("");
    try {
      const response = await adminApiFetch("/admin/totp/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: setupCode }),
      });
      const data = (await readJsonSafely(response)) as MessageResponse | null;
      if (!response.ok) {
        throw new Error(readApiError(data, "2단계 인증을 활성화하지 못했습니다."));
      }
      setManualEntryKey("");
      setSetupCode("");
      setCurrentPassword("");
      await refreshAdmin();
      showMessage(data?.message || "2단계 인증을 활성화했습니다.", "success");
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "2단계 인증을 활성화하지 못했습니다.", "error");
    } finally {
      setLoading(null);
    }
  }

  async function handleDisable(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentPassword || !/^\d{6}$/.test(disableCode)) {
      showMessage("현재 비밀번호와 인증 앱의 6자리 코드를 입력해 주세요.", "error");
      return;
    }

    setLoading("disable");
    setMessage("");
    try {
      const response = await adminApiFetch("/admin/totp", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, code: disableCode }),
      });
      const data = (await readJsonSafely(response)) as MessageResponse | null;
      if (!response.ok) {
        throw new Error(readApiError(data, "2단계 인증을 해제하지 못했습니다."));
      }
      setCurrentPassword("");
      setDisableCode("");
      await refreshAdmin();
      showMessage(data?.message || "2단계 인증을 해제했습니다.", "success");
    } catch (error) {
      showMessage(error instanceof Error ? error.message : "2단계 인증을 해제하지 못했습니다.", "error");
    } finally {
      setLoading(null);
    }
  }

  async function copyManualEntryKey() {
    try {
      await navigator.clipboard.writeText(manualEntryKey);
      showMessage("설정 키를 복사했습니다.", "success");
    } catch {
      showMessage("설정 키를 복사하지 못했습니다. 직접 선택해서 복사해 주세요.", "error");
    }
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  const isEnabled = admin.totp_enabled;

  return (
    <AdminShell>
      <section className="max-w-3xl px-5 py-8 lg:px-9 lg:py-10">
        <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">SECURITY</p>
        <h1 className="mt-2 text-3xl font-extrabold tracking-normal">2단계 인증</h1>
        <p className="mt-2 text-sm text-white/50">관리자 로그인에 인증 앱 코드를 추가합니다.</p>

        <section className="mt-7 rounded-2xl border border-white/10 bg-[#102039]/90 p-5 sm:p-6">
          <div className="flex items-start gap-3">
            <span className={`grid size-10 shrink-0 place-items-center rounded-lg ${isEnabled ? "bg-[#5be3a0]/15 text-[#8af0bd]" : "bg-white/5 text-white/55"}`}>
              <ShieldCheck size={20} />
            </span>
            <div>
              <h2 className="font-bold">현재 상태</h2>
              <p className={`mt-1 text-sm ${isEnabled ? "text-[#8af0bd]" : "text-white/50"}`}>
                {isEnabled ? "2단계 인증 사용 중" : "2단계 인증 미설정"}
              </p>
            </div>
          </div>

          {message && (
            <p role={messageKind === "error" ? "alert" : "status"} className={`mt-5 border px-4 py-3 text-sm ${messageKind === "error" ? "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]" : "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]"}`}>
              {message}
            </p>
          )}
        </section>

        {!isEnabled && !manualEntryKey && (
          <form onSubmit={handleSetup} className="mt-5 rounded-2xl border border-white/10 bg-[#102039]/90 p-5 sm:p-6">
            <h2 className="font-bold">인증 앱 등록 시작</h2>
            <p className="mt-2 text-sm leading-6 text-white/50">Google Authenticator 같은 인증 앱을 준비한 뒤 현재 비밀번호를 입력해 주세요.</p>
            <label className="mt-5 block">
              <span className="mb-2 block text-sm font-bold text-white/75">현재 비밀번호</span>
              <input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" className="h-11 w-full border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]" placeholder="현재 비밀번호" />
            </label>
            <button type="submit" disabled={loading !== null} className="mt-5 inline-flex h-11 items-center gap-2 bg-[#8b5cf6] px-5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60">
              <KeyRound size={17} />
              {loading === "setup" ? "준비 중..." : "설정 키 만들기"}
            </button>
          </form>
        )}

        {!isEnabled && manualEntryKey && (
          <form onSubmit={handleConfirm} className="mt-5 rounded-2xl border border-[#a78bfa]/35 bg-[#102039]/90 p-5 sm:p-6">
            <h2 className="font-bold">인증 앱에 계정 등록</h2>
            <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-white/55">
              <li>Google Authenticator에서 계정 추가를 선택합니다.</li>
              <li>설정 키 입력을 선택하고, 계정 이름은 <span className="text-white/80">AdNova 관리자</span>로 입력합니다.</li>
              <li>아래 설정 키를 붙여넣은 뒤, 앱에 표시된 6자리 코드를 입력합니다.</li>
            </ol>
            <div className="mt-5 flex items-center gap-2 border border-white/15 bg-[#0b1729] p-3">
              <code className="min-w-0 flex-1 break-all text-sm text-[#ddd6fe]">{manualEntryKey}</code>
              <button type="button" onClick={() => void copyManualEntryKey()} className="grid size-9 shrink-0 place-items-center text-white/55 transition hover:bg-white/5 hover:text-white" aria-label="설정 키 복사" title="설정 키 복사">
                <Copy size={17} />
              </button>
            </div>
            <label className="mt-5 block">
              <span className="mb-2 block text-sm font-bold text-white/75">인증 앱 코드</span>
              <input type="text" inputMode="numeric" autoComplete="one-time-code" value={setupCode} onChange={(event) => setSetupCode(onlyTotpDigits(event.target.value))} className="h-11 w-full border border-white/15 bg-[#0b1729] px-3 text-sm tracking-[0.25em] text-white outline-none placeholder:tracking-normal placeholder:text-white/30 focus:border-[#a78bfa]" placeholder="6자리 인증 코드" />
            </label>
            <button type="submit" disabled={loading !== null} className="mt-5 inline-flex h-11 items-center gap-2 bg-[#8b5cf6] px-5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60">
              <ShieldCheck size={17} />
              {loading === "confirm" ? "확인 중..." : "2단계 인증 활성화"}
            </button>
          </form>
        )}

        {isEnabled && (
          <form onSubmit={handleDisable} className="mt-5 rounded-2xl border border-[#f87171]/25 bg-[#102039]/90 p-5 sm:p-6">
            <div className="flex items-start gap-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-[#f87171]/10 text-[#fca5a5]"><ShieldOff size={20} /></span>
              <div>
                <h2 className="font-bold">2단계 인증 해제</h2>
                <p className="mt-1 text-sm leading-6 text-white/50">해제하려면 현재 비밀번호와 인증 앱 코드가 모두 필요합니다.</p>
              </div>
            </div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-2 block text-sm font-bold text-white/75">현재 비밀번호</span>
                <input type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} autoComplete="current-password" className="h-11 w-full border border-white/15 bg-[#0b1729] px-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#f87171]" placeholder="현재 비밀번호" />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm font-bold text-white/75">인증 앱 코드</span>
                <input type="text" inputMode="numeric" autoComplete="one-time-code" value={disableCode} onChange={(event) => setDisableCode(onlyTotpDigits(event.target.value))} className="h-11 w-full border border-white/15 bg-[#0b1729] px-3 text-sm tracking-[0.25em] text-white outline-none placeholder:tracking-normal placeholder:text-white/30 focus:border-[#f87171]" placeholder="6자리 인증 코드" />
              </label>
            </div>
            <button type="submit" disabled={loading !== null} className="mt-5 inline-flex h-11 items-center gap-2 border border-[#f87171]/45 px-5 text-sm font-extrabold text-[#fecaca] transition hover:bg-[#f87171]/10 disabled:cursor-not-allowed disabled:opacity-60">
              <ShieldOff size={17} />
              {loading === "disable" ? "해제 중..." : "2단계 인증 해제"}
            </button>
          </form>
        )}
      </section>
    </AdminShell>
  );
}
