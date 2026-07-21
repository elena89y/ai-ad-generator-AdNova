"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { useAdmin } from "@/components/admin/AdminProvider";
import { adminPublicFetch } from "@/lib/admin-api";
import { readApiError, readJsonSafely } from "@/lib/api";

interface AdminLoginResponse {
  access_token?: string;
}

export default function AdminLoginPage() {
  const router = useRouter();
  const { admin, ready, signIn } = useAdmin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (ready && admin) router.replace("/admin");
  }, [admin, ready, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    if (!username.trim() || !password) {
      setMessage("관리자 아이디와 비밀번호를 입력해 주세요.");
      return;
    }

    setLoading(true);
    try {
      const response = await adminPublicFetch("/auth/admin-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const data = (await readJsonSafely(response)) as AdminLoginResponse | null;

      if (!response.ok || !data?.access_token) {
        throw new Error(readApiError(data, "관리자 로그인에 실패했습니다."));
      }

      await signIn(data.access_token);
      router.replace("/admin");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "관리자 로그인에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[#071426] px-5 py-10 text-[#f8fafc]">
      <section className="w-full max-w-md border border-white/10 bg-[#102039]/90 p-7 shadow-2xl shadow-black/25 sm:p-9">
        <Link href="/" className="inline-flex items-center gap-2 text-sm text-white/50 transition hover:text-white">
          <ArrowLeft size={16} />
          일반 사용자 화면으로
        </Link>

        <div className="mt-10">
          <span className="grid size-11 place-items-center rounded-lg bg-[#8b5cf6] text-white">
            <ShieldCheck size={23} strokeWidth={2.5} />
          </span>
          <p className="mt-6 text-xs font-bold tracking-[0.16em] text-[#a78bfa]">ADNOVA OPERATIONS</p>
          <h1 className="mt-2 text-3xl font-extrabold">관리자 로그인</h1>
          <p className="mt-3 text-sm leading-6 text-white/50">운영 권한이 부여된 계정으로 로그인해 주세요.</p>
        </div>

        {message && (
          <p role="alert" className="mt-6 border border-[#ed6a5e]/35 bg-[#ed6a5e]/10 px-4 py-3 text-sm text-[#ffb0a8]">
            {message}
          </p>
        )}

        <form onSubmit={handleSubmit} className="mt-7 space-y-5">
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-white/75">관리자 아이디</span>
            <input
              type="text"
              autoComplete="username"
              value={username}
              disabled={loading}
              onChange={(event) => setUsername(event.target.value)}
              className="h-12 w-full border border-white/15 bg-[#0b1729] px-4 text-sm outline-none transition placeholder:text-white/25 focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
              placeholder="관리자 아이디"
            />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-white/75">비밀번호</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              disabled={loading}
              onChange={(event) => setPassword(event.target.value)}
              className="h-12 w-full border border-white/15 bg-[#0b1729] px-4 text-sm outline-none transition placeholder:text-white/25 focus:border-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
              placeholder="비밀번호"
            />
          </label>
          <button
            type="submit"
            disabled={loading}
            className="h-12 w-full bg-[#8b5cf6] text-sm font-extrabold text-white transition hover:bg-[#a78bfa] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "로그인 중..." : "관리자 로그인"}
          </button>
        </form>
      </section>
    </main>
  );
}
