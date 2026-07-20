"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { loadUser, setToken } from "@/lib/auth";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const [message, setMessage] = useState("로그인 정보를 확인하고 있습니다.");

  useEffect(() => {
    const handleOAuthCallback = async () => {
      try {
        const hash = window.location.hash.replace(/^#/, "");
        const params = new URLSearchParams(hash);

        const accessToken = params.get("access_token");
        const provider = params.get("provider");
        const userId = params.get("user_id");
        const isNewUser = params.get("is_new_user") === "true";

        console.log("[OAuth Callback]", {
          provider,
          userId,
          isNewUser,
          hasAccessToken: Boolean(accessToken),
        });

        if (!accessToken) {
          throw new Error("OAuth access token이 없습니다.");
        }

        setToken(accessToken);

        const user = await loadUser();

        console.log("[OAuth User]", user);

        if (isNewUser) {
          setMessage("회원가입이 완료되었습니다. 추가 정보를 입력해주세요.");

          router.replace("/onboarding");
          return;
        }

        setMessage("로그인이 완료되었습니다.");

        router.replace("/dashboard");
      } catch (error) {
        console.error("[OAuth Callback Error]", error);

        localStorage.removeItem("access_token");
        localStorage.removeItem("user");

        router.replace(
          `/login?error=${encodeURIComponent(
            "소셜 로그인 처리 중 오류가 발생했습니다."
          )}`
        );
      }
    };

    handleOAuthCallback();
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-6">
      <section className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-sm">
        <div className="mx-auto mb-5 h-10 w-10 animate-spin rounded-full border-4 border-gray-200 border-t-black" />

        <h1 className="text-xl font-semibold text-gray-900">
          소셜 로그인 처리 중
        </h1>

        <p className="mt-3 text-sm text-gray-600">{message}</p>
      </section>
    </main>
  );
}
