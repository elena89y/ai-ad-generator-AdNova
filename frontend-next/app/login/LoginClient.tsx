"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type SyntheticEvent } from "react";

import { authApi } from "@/lib/auth-api";
import { loadUser, setToken } from "@/lib/auth";
import {
  apiFetch,
  getToken,
  isPersistentAuth,
  readApiError,
  readJsonSafely,
  refreshAccessToken,
  storeAuth,
} from "@/lib/api";

type OAuthProvider = "google" | "kakao" | "naver";

export default function LoginClient() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [rememberMe, setRememberMe] = useState(false);
  const [message, setMessage] = useState(
    searchParams.get("message") ||
      searchParams.get("oauth_error") ||
      ""
  );
  const [isLoading, setIsLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function redirectIfSignedIn() {
      try {
        const activeToken = getToken() || (await refreshAccessToken());
        if (!activeToken) return;

        const response = await apiFetch("/api/account/me");
        const user = await readJsonSafely(response);
        const verifiedToken = getToken();
        if (!response.ok || !verifiedToken || !user || cancelled) return;

        storeAuth(verifiedToken, user as Parameters<typeof storeAuth>[1], isPersistentAuth());
        router.replace("/dashboard");
      } catch {
        // 로그인 화면에서는 네트워크 오류를 일반 로그인 가능 상태로 처리합니다.
      } finally {
        if (!cancelled) setCheckingSession(false);
      }
    }

    void redirectIfSignedIn();
    return () => {
      cancelled = true;
    };
  }, [router]);

  function startOAuth(provider: OAuthProvider): void {
    /*
     * 배포 후에는 현재 도메인의 /api가 Nginx를 통해
     * FastAPI로 전달됩니다.
     *
     * localhost:3000에서 프록시 설정 없이 실행하면
     * /api/auth/... 주소는 404가 나오는 것이 정상입니다.
     */
    if (isLoading) return;
    setIsLoading(true);
    window.location.href = `/api/auth/${provider}/login`;
  }

  async function handleLogin(
    event: SyntheticEvent<HTMLFormElement>
  ): Promise<void> {
    event.preventDefault();

    const loginId = username.trim();

    if (!loginId) {
      setMessage("아이디를 입력해 주세요.");
      return;
    }

    if (!password) {
      setMessage("비밀번호를 입력해 주세요.");
      return;
    }

    setIsLoading(true);
    setMessage("");

    try {
      const response = await authApi.post("/auth/login", {
        username: loginId,
        password,
        remember_me: rememberMe,
      });

      const accessToken = response.data?.access_token;

      if (!accessToken) {
        throw new Error("로그인 토큰을 받지 못했습니다.");
      }

      setToken(accessToken, rememberMe);

      const user = await loadUser();

      /*
       * 백엔드 사용자 응답에 온보딩 여부가 있다면 이를 기준으로 이동합니다.
       * 필드명이 다를 경우 실제 /account/me 응답에 맞춰 조정하면 됩니다.
       */
      const needsOnboarding =
        user?.is_new_user === true ||
        user?.onboarding_completed === false ||
        user?.is_onboarded === false;

      window.location.replace(needsOnboarding
        ? "/onboarding"
        : "/dashboard");
    } catch (error: unknown) {
      const fallbackMessage =
        error instanceof Error
          ? error.message
          : "로그인에 실패했습니다.";

      const apiErrorData =
        typeof error === "object" &&
        error !== null &&
        "response" in error
          ? (
              error as {
                response?: {
                  data?: unknown;
                };
              }
            ).response?.data
          : undefined;

      setMessage(readApiError(apiErrorData, fallbackMessage));
    } finally {
      setIsLoading(false);
    }
  }

  if (checkingSession) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[var(--auth-background)] px-5 text-sm text-white/60">
        로그인 상태를 확인하는 중입니다.
      </main>
    );
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[var(--auth-background)] px-5 py-10 text-[var(--foreground)]">
      {/* 배경 장식 */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
      >
        <div
          className="absolute left-1/2 top-[-180px] h-[430px] w-[700px] -translate-x-1/2 rounded-full blur-[140px]"
          style={{ background: "var(--auth-glow)" }}
        />

        <div
          className="absolute bottom-[-220px] right-[-160px] h-[500px] w-[500px] rounded-full blur-[150px]"
          style={{ background: "var(--auth-glow-deep)" }}
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
          ← 홈으로
        </Link>

        <div className="mb-8">
          <Link href="/" className="inline-flex items-center">
            <Image
              src="/brand/brand-logo.png"
              alt="AdNova"
              width={154}
              height={42}
              priority
              className="h-auto w-[145px] object-contain"
            />
          </Link>

          <h1 className="mt-7 text-3xl font-extrabold tracking-[-0.04em]">
            다시 오신 것을 환영해요
          </h1>

          <p className="mt-2 text-sm leading-6 text-white/50">
            AdNova 계정으로 로그인해 주세요.
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

        <form onSubmit={handleLogin} className="space-y-5">
          <div>
            <label
              htmlFor="loginUsername"
              className="mb-2 block text-sm font-semibold text-white/75"
            >
              아이디
            </label>

            <input
              id="loginUsername"
              type="text"
              autoComplete="username"
              placeholder="아이디를 입력하세요"
              value={username}
              disabled={isLoading}
              onChange={(event) =>
                setUsername(event.target.value)
              }
              className="auth-input h-12 w-full rounded-xl px-4 text-sm outline-none transition disabled:cursor-not-allowed disabled:opacity-60"
            />
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label
                htmlFor="loginPassword"
                className="text-sm font-semibold text-white/75"
              >
                비밀번호
              </label>

              <Link
                href="/forgot"
                className="text-xs font-medium text-white/40 transition hover:text-[var(--accent-deep)]"
              >
                비밀번호 찾기
              </Link>
            </div>

            <input
              id="loginPassword"
              type="password"
              autoComplete="current-password"
              placeholder="비밀번호를 입력하세요"
              value={password}
              disabled={isLoading}
              onChange={(event) =>
                setPassword(event.target.value)
              }
              className="auth-input h-12 w-full rounded-xl px-4 text-sm outline-none transition disabled:cursor-not-allowed disabled:opacity-60"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-white/55">
            <input
              type="checkbox"
              checked={rememberMe}
              disabled={isLoading}
              onChange={(event) => setRememberMe(event.target.checked)}
              className="size-4 accent-[var(--accent-deep)]"
            />
            로그인 유지
          </label>

          <button
            type="submit"
            disabled={isLoading}
            className="h-12 w-full rounded-xl text-sm font-extrabold text-white transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
            style={{
              background: "var(--auth-gradient)",
              boxShadow: "0 12px 30px var(--auth-glow)",
            }}
          >
            {isLoading ? "로그인 중..." : "로그인"}
          </button>
        </form>

        <div className="my-7 flex items-center gap-3">
          <span className="h-px flex-1 bg-white/10" />
          <span className="text-xs text-white/30">또는</span>
          <span className="h-px flex-1 bg-white/10" />
        </div>

        <div className="space-y-3">
          <button
            type="button"
            disabled={isLoading}
            onClick={() => startOAuth("google")}
            className="relative flex h-12 w-full items-center justify-center rounded-xl border border-white/10 bg-white/[0.035] text-sm font-semibold text-white/75 transition hover:border-white/20 hover:bg-white/[0.07] disabled:opacity-60"
          >
            <span className="absolute left-4 flex h-7 w-7 items-center justify-center rounded-md bg-white">
              <Image
                src="/assets/icons/google.svg"
                alt=""
                width={17}
                height={17}
              />
            </span>
            Google로 계속하기
          </button>

          <button
            type="button"
            disabled={isLoading}
            onClick={() => startOAuth("kakao")}
            className="relative flex h-12 w-full items-center justify-center rounded-xl border border-white/10 bg-white/[0.035] text-sm font-semibold text-white/75 transition hover:border-white/20 hover:bg-white/[0.07] disabled:opacity-60"
          >
            <span className="absolute left-4 flex h-7 w-7 items-center justify-center rounded-md bg-[#fee500]">
              <Image
                src="/assets/icons/kakao.png"
                alt=""
                width={17}
                height={17}
              />
            </span>
            카카오로 계속하기
          </button>

          <button
            type="button"
            disabled={isLoading}
            onClick={() => startOAuth("naver")}
            className="relative flex h-12 w-full items-center justify-center rounded-xl border border-white/10 bg-white/[0.035] text-sm font-semibold text-white/75 transition hover:border-white/20 hover:bg-white/[0.07] disabled:opacity-60"
          >
            <span className="absolute left-4 flex h-7 w-7 items-center justify-center rounded-md bg-[#03c75a]">
              <Image
                src="/assets/icons/naver.png"
                alt=""
                width={17}
                height={17}
              />
            </span>
            네이버로 계속하기
          </button>
        </div>

        <p className="mt-8 text-center text-sm text-white/40">
          아직 계정이 없으세요?{" "}
          <Link
            href="/signup"
            className="font-bold text-[var(--accent-deep)] transition hover:text-[var(--accent)]"
          >
            무료로 시작하기
          </Link>
        </p>
      </section>
    </main>
  );
}
