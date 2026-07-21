"use client";

/* v6 T4 — 템플릿 갤러리 (카탈로그 v1 46종, 모노브식).
   좌측 워크스페이스 내비(광고 이미지/템플릿) + 태그 필터 칩 + 카드 클릭 → 중앙 확대 모달.
   데이터는 정적 카탈로그(lib/catalog.ts) — 생성 프롬프트는 클라이언트에 싣지 않는다.
   CTA: 카드 → /templates/{id} 전용 페이지(TEMPLATE-PIPE-V2 서버측 연출 레시피). */

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CATALOG, CatalogTemplate } from "@/lib/catalog";
import { useStudio } from "@/components/studio/StudioProvider";
import { AppBar, WorkspaceNav } from "@/components/studio/chrome";

const FINISH_LABEL: Record<string, string> = {
  photographic: "실사 마감",
  graphic: "그래픽 마감",
  stylized: "무드 연출",
};

export default function TemplatesPage() {
  const s = useStudio();
  const router = useRouter();
  const [tag, setTag] = useState("전체");
  const [picked, setPicked] = useState<CatalogTemplate | null>(null);

  useEffect(() => {
    if (s.ready && !s.token) router.replace("/login");
  }, [s.ready, s.token, router]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPicked(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const tags = useMemo(() => {
    const freq = new Map<string, number>();
    CATALOG.forEach((t) => t.tags.forEach((tg) => freq.set(tg, (freq.get(tg) ?? 0) + 1)));
    return ["전체", ...[...freq.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k)];
  }, []);

  const shown = useMemo(
    () => (tag === "전체" ? CATALOG : CATALOG.filter((t) => t.tags.includes(tag))),
    [tag]
  );

  const startWith = (t: CatalogTemplate) => {
    // TEMPLATE-PIPE-V2: 전용 페이지로 진입 → 서버측 연출 레시피(template_id)로 생성.
    // studio(스타일 프리셋) 경로로 흘려보내던 기존 배선 폐기.
    router.push(`/templates/${encodeURIComponent(t.id)}`);
  };

  return (
    <section>
      <AppBar />
      <div className="workspace-shell">
        <WorkspaceNav />
        <main style={{ flex: 1, minWidth: 0, padding: "24px 26px 60px" }}>
          <h1 style={{ fontSize: 21, fontWeight: 800, marginBottom: 4 }}>템플릿</h1>
          <p style={{ fontSize: 13, color: "var(--ink-mute)", marginBottom: 14 }}>
            원하는 연출을 고르면 스타일·용도가 자동으로 설정돼요. 제품 사진 1장이면 충분합니다.
          </p>

          {/* 태그 필터 칩 — 가로 스크롤 대신 창 폭에 맞춰 여러 줄로 감싼다 */}
          <div
            style={{
              display: "flex",
              gap: 7,
              flexWrap: "wrap",
              paddingBottom: 10,
              marginBottom: 16,
            }}
          >
            {tags.map((tg) => {
              const on = tg === tag;
              return (
                <button
                  key={tg}
                  type="button"
                  onClick={() => setTag(tg)}
                  style={{
                    flex: "0 0 auto",
                    padding: "6px 13px",
                    borderRadius: 999,
                    fontSize: 12,
                    fontWeight: 700,
                    cursor: "pointer",
                    border: on ? "1px solid var(--gold)" : "1px solid var(--line)",
                    background: on ? "rgba(242,169,59,.14)" : "rgba(255,255,255,.04)",
                    color: on ? "var(--gold)" : "var(--ink-soft)",
                  }}
                >
                  {tg}
                </button>
              );
            })}
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(185px, 1fr))",
              gap: 15,
            }}
          >
            {shown.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setPicked(t)}
                style={{
                  textAlign: "left",
                  padding: 0,
                  border: "1px solid var(--line)",
                  borderRadius: 14,
                  overflow: "hidden",
                  background: "rgba(255,255,255,.03)",
                  cursor: "pointer",
                }}
              >
                <div style={{ width: "100%", aspectRatio: "2 / 3", overflow: "hidden" }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={t.img}
                    alt={t.name}
                    loading="lazy"
                    style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                  />
                </div>
                <div style={{ padding: "9px 11px 11px" }}>
                  <div style={{ fontSize: 13, fontWeight: 800 }}>{t.name}</div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "var(--ink-mute)",
                      marginTop: 3,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {t.desc}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </main>
      </div>

      {/* 중앙 확대 프리뷰 모달 */}
      {picked && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            if (e.target === e.currentTarget) setPicked(null);
          }}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 90,
            background: "rgba(10,8,16,.74)",
            backdropFilter: "blur(6px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 22,
          }}
        >
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              width: "min(880px, 94vw)",
              maxHeight: "90vh",
              background: "#17151c",
              border: "1px solid var(--line)",
              borderRadius: 18,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                flex: "1 1 320px",
                minWidth: 260,
                background: "#0d0b12",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={picked.img}
                alt={picked.name}
                style={{ width: "100%", height: "100%", maxHeight: "90vh", objectFit: "contain" }}
              />
            </div>
            <div
              style={{
                flex: "1 1 300px",
                padding: "24px 22px",
                display: "flex",
                flexDirection: "column",
                gap: 11,
                minWidth: 260,
              }}
            >
              <button
                type="button"
                aria-label="닫기"
                onClick={() => setPicked(null)}
                style={{
                  alignSelf: "flex-end",
                  border: 0,
                  background: "transparent",
                  color: "var(--ink-mute)",
                  fontSize: 16,
                  cursor: "pointer",
                }}
              >
                ✕
              </button>
              <div style={{ fontSize: 19, fontWeight: 800 }}>{picked.name}</div>
              <div style={{ fontSize: 13, lineHeight: 1.65, color: "var(--ink-soft)" }}>
                {picked.desc}
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {picked.tags.map((tg) => (
                  <button
                    key={tg}
                    type="button"
                    onClick={() => {
                      setTag(tg);
                      setPicked(null);
                    }}
                    style={{
                      fontSize: 11,
                      padding: "3px 9px",
                      borderRadius: 999,
                      border: "1px solid var(--line)",
                      background: "rgba(255,255,255,.06)",
                      color: "var(--ink-soft)",
                      cursor: "pointer",
                    }}
                  >
                    {tg}
                  </button>
                ))}
              </div>
              <div style={{ fontSize: 11.5, color: "var(--ink-mute)" }}>
                {FINISH_LABEL[picked.finish] ?? picked.finish}
              </div>
              <button className="btn-gen" style={{ marginTop: "auto" }} onClick={() => startWith(picked)}>
                ✦ 이 템플릿으로 광고 만들기
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
