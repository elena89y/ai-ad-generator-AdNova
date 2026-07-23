"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { PASSWORD_PATTERN, apiFetch, readApiError, readJsonSafely } from "@/lib/api";
import { useStudio } from "@/components/studio/StudioProvider";
import { Brand } from "@/components/studio/chrome";

function ResetPasswordContent() {
  const { toast } = useStudio();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!token) return toast("재설정 링크가 올바르지 않습니다");
    if (!PASSWORD_PATTERN.test(newPassword)) {
      return toast("비밀번호는 8~20자이며 대문자, 소문자, 숫자, 특수문자를 포함해야 합니다");
    }
    if (newPassword !== confirmPassword) return toast("새 비밀번호가 서로 다릅니다");

    setBusy(true);
    try {
      const res = await apiFetch("/api/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      const data = (await readJsonSafely(res)) as { message?: string } | null;
      if (!res.ok) throw new Error(readApiError(data, "비밀번호를 변경하지 못했습니다"));
      toast(data?.message || "비밀번호가 변경되었습니다");
      router.replace("/login");
    } catch (err) {
      toast(err instanceof Error ? err.message : "비밀번호를 변경하지 못했습니다");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="auth-screen">
      <div className="login-left">
        <Link href="/login" className="back-link">← 로그인으로</Link>
        <Brand large />
        <h1>새 비밀번호를<br />설정해 주세요.</h1>
        <p className="sub">새 비밀번호를 입력하면<br />다시 로그인할 수 있어요.</p>
        <div className="field">
          <label htmlFor="resetNewPassword">새 비밀번호</label>
          <input
            id="resetNewPassword"
            type="password"
            autoComplete="new-password"
            placeholder="8~20자, 대소문자·숫자·특수문자 포함"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="resetConfirmPassword">새 비밀번호 확인</label>
          <input
            id="resetConfirmPassword"
            type="password"
            autoComplete="new-password"
            placeholder="새 비밀번호를 다시 입력해 주세요"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void submit(); }}
          />
        </div>
        <button className="btn-primary" disabled={busy} onClick={() => void submit()}>
          {busy ? "변경 중..." : "비밀번호 변경"}
        </button>
      </div>
      <div className="login-right">
        <div className="spotlight" />
        <div className="showcase">
          <span className="tag">✦ 다시 시작해요</span>
          <div className="ad-preview">
            <div className="pic"><span className="badge">새 출발</span><div className="prod">☕</div></div>
            <div className="cap"><h4>하루의 첫 여유</h4><p>새 비밀번호로 안전하게 돌아와요</p></div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function ResetPasswordPage() {
  return <Suspense><ResetPasswordContent /></Suspense>;
}
