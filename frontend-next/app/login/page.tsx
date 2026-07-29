import { Suspense } from "react";
import LoginClient from "./LoginClient";

export default function LoginPage() {
  return (
    <Suspense fallback={<LoginFallback />}>
      <LoginClient />
    </Suspense>
  );
}

function LoginFallback() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[var(--auth-background)] text-[var(--foreground)]">
      <div className="text-sm text-[var(--muted)]">
        로그인 화면을 불러오는 중...
      </div>
    </main>
  );
}