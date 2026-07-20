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
    <main className="flex min-h-screen items-center justify-center bg-[#0e0e11] text-white">
      <div className="text-sm text-white/50">로그인 화면을 불러오는 중...</div>
    </main>
  );
}