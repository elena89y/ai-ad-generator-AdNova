"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";

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
  const [showPassword, setShowPassword] = useState(false);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (ready && admin) {
      router.replace("/admin");
    }
  }, [admin, ready, router]);

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();
    setMessage("");

    if (!username.trim() || !password) {
      setMessage(
        "관리자 아이디와 비밀번호를 입력해 주세요."
      );
      return;
    }

    setLoading(true);

    try {
      const response = await adminPublicFetch(
        "/auth/admin-login",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            username: username.trim(),
            password,
          }),
        }
      );

      const data =
        (await readJsonSafely(
          response
        )) as AdminLoginResponse | null;

      if (!response.ok || !data?.access_token) {
        throw new Error(
          readApiError(
            data,
            "관리자 로그인에 실패했습니다."
          )
        );
      }

      await signIn(data.access_token);
      router.replace("/admin");
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : "관리자 로그인에 실패했습니다."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[var(--auth-background)] px-5 py-10 text-[var(--foreground)]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
      >
        <div
          className="absolute left-1/2 top-[-180px] h-[430px] w-[700px] -translate-x-1/2 rounded-full blur-[140px]"
          style={{
            background: "var(--auth-glow)",
          }}
        />

        <div
          className="absolute bottom-[-220px] right-[-160px] h-[500px] w-[500px] rounded-full blur-[150px]"
          style={{
            background: "var(--auth-glow-deep)",
          }}
        />

        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_0%,rgba(0,0,0,0.3)_70%,rgba(0,0,0,0.6)_100%)]" />
      </div>

      <section
        className="relative z-10 w-full max-w-[430px] rounded-[24px] border p-8 shadow-[0_30px_90px_rgba(0,0,0,0.55)] backdrop-blur-xl sm:p-10"
        style={{
          background: "var(--auth-panel)",
          borderColor: "var(--auth-border)",
        }}
      >
        <Link
          href="/"
          className="mb-8 inline-flex items-center gap-2 text-xs font-medium text-white/45 transition hover:text-white/80"
        >
          ← 일반 사용자 화면으로
        </Link>

        <div className="mb-8">
          <Link
            href="/"
            className="inline-flex items-center"
          >
            <Image
              src="/brand/brand-logo.png"
              alt="AdNova"
              width={154}
              height={42}
              priority
              className="h-auto w-[145px] object-contain"
            />
          </Link>

          <p className="mt-7 text-xs font-bold tracking-[0.16em] text-[var(--accent-deep)]">
            ADNOVA OPERATIONS
          </p>

          <h1 className="mt-2 text-3xl font-extrabold tracking-[-0.04em]">
            관리자 로그인
          </h1>

          <p className="mt-2 text-sm leading-6 text-white/50">
            운영 권한이 부여된 계정으로 로그인해
            주세요.
          </p>
        </div>

        {message && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-[#e0567f]/25 bg-[#e0567f]/10 px-4 py-3 text-sm leading-5 text-[#ff9dbb]"
          >
            {message}
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          className="space-y-5"
        >
          <div>
            <label
              htmlFor="adminUsername"
              className="mb-2 block text-sm font-semibold text-white/75"
            >
              관리자 아이디
            </label>

            <input
              id="adminUsername"
              type="text"
              autoComplete="username"
              value={username}
              disabled={loading}
              onChange={(event) =>
                setUsername(event.target.value)
              }
              className="auth-input h-12 w-full rounded-xl px-4 text-sm outline-none transition disabled:cursor-not-allowed disabled:opacity-60"
              placeholder="관리자 아이디를 입력하세요"
            />
          </div>

          <div>
            <label
              htmlFor="adminPassword"
              className="mb-2 block text-sm font-semibold text-white/75"
            >
              비밀번호
            </label>

            <div className="relative">
              <input
                id="adminPassword"
                type={
                  showPassword ? "text" : "password"
                }
                autoComplete="current-password"
                value={password}
                disabled={loading}
                onChange={(event) =>
                  setPassword(event.target.value)
                }
                className="auth-input h-12 w-full rounded-xl px-4 pr-12 text-sm outline-none transition disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="비밀번호를 입력하세요"
              />

              <button
                type="button"
                onClick={() =>
                  setShowPassword(
                    (current) => !current
                  )
                }
                disabled={loading}
                className="absolute right-3 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-lg text-white/35 transition hover:bg-white/5 hover:text-white/75 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-deep)] disabled:cursor-not-allowed disabled:opacity-50"
                aria-label={
                  showPassword
                    ? "비밀번호 숨기기"
                    : "비밀번호 보기"
                }
                title={
                  showPassword
                    ? "비밀번호 숨기기"
                    : "비밀번호 보기"
                }
              >
                {showPassword ? (
                  <EyeOff
                    size={18}
                    aria-hidden="true"
                  />
                ) : (
                  <Eye
                    size={18}
                    aria-hidden="true"
                  />
                )}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="h-12 w-full rounded-xl text-sm font-extrabold text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            style={{
              background: "var(--auth-gradient)",
              boxShadow:
                "0 12px 30px var(--auth-glow)",
            }}
          >
            {loading
              ? "로그인 중..."
              : "관리자 로그인"}
          </button>
        </form>

        <p className="mt-7 text-center text-xs leading-5 text-white/35">
          관리자 계정은 운영 권한이 부여된 사용자만
          이용할 수 있습니다.
        </p>
      </section>
    </main>
  );
}