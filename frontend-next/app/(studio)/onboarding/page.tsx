"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Brand } from "@/components/studio/chrome";
import { useStudio } from "@/components/studio/StudioProvider";

const steps = [
  { n: "1", title: "제품 사진 올리기", desc: "배경은 자동으로 제거돼요", active: true },
  { n: "2", title: "스타일 & 용도 고르기", desc: "AI 추천 또는 직접 입력", active: false },
  {
    n: "3",
    title: "생성 · 저장 · 공유",
    desc: "이력에 저장, 프리미엄은 원본 다운로드",
    active: false,
  },
];

export default function OnboardingPage() {
  const router = useRouter();
  const studio = useStudio();

  useEffect(() => {
    if (studio.ready && !studio.token) router.replace("/login");
  }, [router, studio.ready, studio.token]);

  if (!studio.ready || !studio.token) {
    return <main className="onb-wrap">로그인 정보를 확인하는 중입니다.</main>;
  }

  return (
    <div className="onb-wrap">
      <div
        style={{
          width: "min(100%,520px)",
          background: "var(--card)",
          border: "1px solid var(--line)",
          borderRadius: 20,
          boxShadow: "var(--shadow-lg)",
          padding: 30,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            marginBottom: 20,
          }}
        >
          <Brand large />
        </div>
        <div style={{ textAlign: "center", marginBottom: 24 }}>
          <h2
            style={{
              fontSize: 22,
              fontWeight: 800,
              letterSpacing: "-.5px",
              marginBottom: 6,
            }}
          >
            환영해요! 3단계면 끝나요
          </h2>
          <p style={{ fontSize: 13, color: "var(--ink-mute)" }}>
            가입 축하 <b style={{ color: "var(--gold)" }}>크레딧 3개</b>를 드렸어요.
          </p>
        </div>
        <div
          style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 24 }}
        >
          {steps.map((s) => (
            <div
              key={s.n}
              style={{
                display: "flex",
                gap: 14,
                alignItems: "center",
                padding: 14,
                background: "#26242D",
                border: `1px solid ${s.active ? "rgba(242,169,59,.25)" : "var(--line)"}`,
                borderRadius: 13,
              }}
            >
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 10,
                  background: s.active ? "rgba(242,169,59,.16)" : "rgba(255,255,255,.06)",
                  color: s.active ? "var(--gold)" : "var(--ink-soft)",
                  display: "grid",
                  placeItems: "center",
                  fontWeight: 800,
                  fontFamily: "var(--disp)",
                  flex: "none",
                }}
              >
                {s.n}
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{s.title}</div>
                <div style={{ fontSize: 12, color: "var(--ink-mute)" }}>{s.desc}</div>
              </div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", gap: 6 }}>
            <span
              style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--gold)" }}
            />
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "rgba(255,255,255,.16)",
              }}
            />
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "rgba(255,255,255,.16)",
              }}
            />
          </div>
          <Link href="/studio" className="back-link" style={{ margin: 0 }}>
            건너뛰기
          </Link>
          <Link
            href="/studio"
            style={{
              marginLeft: "auto",
              padding: "12px 22px",
              border: "none",
              borderRadius: 11,
              background: "var(--gold)",
              color: "#16151A",
              fontSize: 14,
              fontWeight: 700,
              cursor: "pointer",
              textDecoration: "none",
            }}
          >
            첫 광고 만들기 →
          </Link>
        </div>
      </div>
    </div>
  );
}
