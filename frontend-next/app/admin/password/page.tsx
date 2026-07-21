"use client";

import { type FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, KeyRound, ShieldCheck } from "lucide-react";
import { AdminShell } from "@/components/admin/AdminShell";
import { useAdmin } from "@/components/admin/AdminProvider";
import { adminApiFetch } from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

type MessageResponse = { message?: string };

export default function AdminPasswordPage() {
  const router = useRouter();
  const { admin, ready } = useAdmin();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error" | null>(null);

  useEffect(() => {
    if (ready && !admin) router.replace("/admin/login");
  }, [admin, ready, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!currentPassword || !newPassword || !confirmPassword) {
      setMessage("현재 비밀번호와 새 비밀번호를 모두 입력해 주세요.");
      setMessageKind("error");
      return;
    }
    if (newPassword !== confirmPassword) {
      setMessage("새 비밀번호와 확인 값이 일치하지 않습니다.");
      setMessageKind("error");
      return;
    }

    setLoading(true);
    setMessage("");
    setMessageKind(null);
    try {
      const response = await adminApiFetch("/admin/password", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      const data = (await readJsonSafely(response)) as MessageResponse | null;
      if (!response.ok) {
        throw new Error(readApiError(data, "비밀번호를 변경하지 못했습니다."));
      }
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setMessage(data?.message || "비밀번호를 변경했습니다.");
      setMessageKind("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "비밀번호를 변경하지 못했습니다.");
      setMessageKind("error");
    } finally {
      setLoading(false);
    }
  }

  if (!ready || !admin) {
    return <main className="grid min-h-screen place-items-center bg-[#071426] text-sm text-white/55">관리자 인증을 확인하고 있습니다.</main>;
  }

  return (
    <AdminShell>
      <section className="max-w-3xl px-5 py-8 lg:px-9 lg:py-10">
        <p className="text-xs font-bold tracking-[0.16em] text-[#a78bfa]">SECURITY</p>
        <h1 className="mt-2 text-3xl font-extrabold tracking-normal">비밀번호 변경</h1>
        <p className="mt-2 text-sm text-white/50">관리자 계정의 비밀번호를 변경합니다.</p>

        <form onSubmit={handleSubmit} className="mt-7 border border-white/10 bg-[#102039]/90 p-5 sm:p-6">
          <div className="flex items-start gap-3 border-b border-white/10 pb-5">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-[#8b5cf6]/15 text-[#c4b5fd]">
              <ShieldCheck size={20} />
            </span>
            <div>
              <h2 className="font-bold">계정 보안</h2>
              <p className="mt-1 text-sm leading-6 text-white/50">새 비밀번호는 8~20자이며 대문자, 소문자, 숫자, 특수문자를 모두 포함해야 합니다.</p>
            </div>
          </div>

          <div className="mt-6 space-y-5">
            <label className="block">
              <span className="mb-2 block text-sm font-bold text-white/75">현재 비밀번호</span>
              <span className="relative block">
                <input
                  type={showCurrentPassword ? "text" : "password"}
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  autoComplete="current-password"
                  className="h-11 w-full border border-white/15 bg-[#0b1729] px-3 pr-11 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
                />
                <button
                  type="button"
                  onClick={() => setShowCurrentPassword((current) => !current)}
                  className="absolute inset-y-0 right-0 grid w-11 place-items-center text-white/45 transition hover:text-white"
                  aria-label={showCurrentPassword ? "현재 비밀번호 숨기기" : "현재 비밀번호 보기"}
                  title={showCurrentPassword ? "비밀번호 숨기기" : "비밀번호 보기"}
                >
                  {showCurrentPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </span>
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-bold text-white/75">새 비밀번호</span>
              <span className="relative block">
                <input
                  type={showNewPassword ? "text" : "password"}
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={20}
                  placeholder="8~20자, 대소문자·숫자·특수문자 포함"
                  className="h-11 w-full border border-white/15 bg-[#0b1729] px-3 pr-11 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword((current) => !current)}
                  className="absolute inset-y-0 right-0 grid w-11 place-items-center text-white/45 transition hover:text-white"
                  aria-label={showNewPassword ? "새 비밀번호 숨기기" : "새 비밀번호 보기"}
                  title={showNewPassword ? "비밀번호 숨기기" : "비밀번호 보기"}
                >
                  {showNewPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </span>
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-bold text-white/75">새 비밀번호 확인</span>
              <span className="relative block">
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  autoComplete="new-password"
                  className="h-11 w-full border border-white/15 bg-[#0b1729] px-3 pr-11 text-sm text-white outline-none placeholder:text-white/30 focus:border-[#a78bfa]"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword((current) => !current)}
                  className="absolute inset-y-0 right-0 grid w-11 place-items-center text-white/45 transition hover:text-white"
                  aria-label={showConfirmPassword ? "새 비밀번호 확인 숨기기" : "새 비밀번호 확인 보기"}
                  title={showConfirmPassword ? "비밀번호 숨기기" : "비밀번호 보기"}
                >
                  {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </span>
            </label>
          </div>

          {message && (
            <p
              role={messageKind === "error" ? "alert" : "status"}
              className={`mt-6 border px-4 py-3 text-sm ${
                messageKind === "error"
                  ? "border-[#f87171]/35 bg-[#f87171]/10 text-[#fecaca]"
                  : "border-[#5be3a0]/35 bg-[#5be3a0]/10 text-[#8af0bd]"
              }`}
            >
              {message}
            </p>
          )}

          <div className="mt-6 flex justify-end">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex h-11 items-center gap-2 bg-[#8b5cf6] px-5 text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <KeyRound size={17} />
              {loading ? "변경 중..." : "비밀번호 변경"}
            </button>
          </div>
        </form>
      </section>
    </AdminShell>
  );
}
