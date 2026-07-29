"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  apiFetch,
  getItemPlatformCopy,
  historyToCard,
  readApiError,
  readJsonSafely,
} from "@/lib/api";
import { PLATFORM_NAMES, exportSnsPost } from "@/lib/sns";
import { useStudio } from "@/components/studio/StudioProvider";
import { Brand } from "@/components/studio/chrome";
import { AuthenticatedImage } from "@/components/studio/AuthenticatedImage";

const TABS = [
  { p: "instagram", label: "Instagram", ig: true },
  { p: "facebook", label: "Facebook" },
  { p: "x", label: "X" },
  { p: "threads", label: "Threads" },
];

function ShareContent() {
  const s = useStudio();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [platform, setPlatform] = useState(s.sharePlatform || "instagram");
  const [verifiedHistoryId, setVerifiedHistoryId] = useState<number | null>(null);
  const [verifying, setVerifying] = useState(false);
  const requestedHistoryId = Number(searchParams.get("historyId"));
  const historyId = Number.isInteger(requestedHistoryId) && requestedHistoryId > 0
    ? requestedHistoryId
    : null;
  const item = s.activeItem;

  useEffect(() => {
    if (!s.ready) return;
    if (!s.token) {
      router.replace("/login");
      return;
    }
    if (!historyId && !item) {
      router.replace("/studio");
      return;
    }
    if (historyId && item?.historyId !== historyId) {
      let cancelled = false;
      setVerifying(true);

      async function loadSharedAd() {
        try {
          const response = await apiFetch(`/api/history/${historyId}`);
          const data = await readJsonSafely(response);
          if (!response.ok) {
            throw new Error(readApiError(data, "공유할 광고를 불러올 수 없습니다"));
          }
          if (!cancelled) {
            s.openDetail(historyToCard(data as Parameters<typeof historyToCard>[0]));
            setVerifiedHistoryId(historyId);
          }
        } catch (error) {
          if (!cancelled) {
            s.toast(error instanceof Error ? error.message : "공유할 광고를 불러올 수 없습니다");
            router.replace("/my-ads");
          }
        } finally {
          if (!cancelled) setVerifying(false);
        }
      }

      void loadSharedAd();
      return () => {
        cancelled = true;
      };
    }

    if (!item) return;
    const itemHistoryId = item.historyId ?? null;
    if (!itemHistoryId || verifiedHistoryId === itemHistoryId) return;

    let cancelled = false;
    setVerifying(true);

    async function verifyOwnership() {
      try {
        const response = await apiFetch(`/api/history/${itemHistoryId}`);
        const data = await readJsonSafely(response);
        if (!response.ok) {
          throw new Error(readApiError(data, "공유할 광고를 확인할 수 없습니다"));
        }
        if (!cancelled) setVerifiedHistoryId(itemHistoryId ?? null);
      } catch (error) {
        if (!cancelled) {
          s.toast(error instanceof Error ? error.message : "공유할 광고를 확인할 수 없습니다");
          router.replace("/my-ads");
        }
      } finally {
        if (!cancelled) setVerifying(false);
      }
    }

    void verifyOwnership();
    return () => {
      cancelled = true;
    };

  }, [historyId, item, item?.historyId, router, s, verifiedHistoryId]);

  if (!s.ready || !s.token || !item || verifying || (item.historyId && verifiedHistoryId !== item.historyId)) {
    return <div className="page">공유 정보를 확인하는 중입니다.</div>;
  }
  const copy = getItemPlatformCopy(item, platform);

  async function shareNow() {
    if (!item) return;
    await exportSnsPost(
      platform,
      { ...item, copyHead: copy.head, copyBody: copy.body, copyTags: copy.tags },
      s.toast
    );
  }

  return (
    <section>
      <div className="subbar">
        <Brand />
        <Link
          href={historyId ? `/detail?historyId=${historyId}` : s.shareFrom || "/studio"}
          className="back-link"
          style={{ margin: "0 0 0 6px" }}
        >
          ← 뒤로
        </Link>
      </div>
      <div className="page" style={{ maxWidth: 560 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 16 }}>
          <h2 style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-.5px" }}>
            공유 &amp; 내보내기
          </h2>
          <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--ink-mute)" }}>
            이력에 저장됨 ✓
          </span>
        </div>
        <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
          {TABS.map((t) => (
            <button
              key={t.p}
              className={`shtab${platform === t.p ? " on" : ""}`}
              onClick={() => setPlatform(t.p)}
            >
              {t.ig && (
                <span
                  style={{
                    width: 15,
                    height: 15,
                    borderRadius: 4,
                    background: "linear-gradient(135deg,#f9ce34,#ee2a7b,#6228d7)",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 8,
                    color: "#fff",
                    fontWeight: 800,
                  }}
                >
                  IG
                </span>
              )}
              {t.label}
            </button>
          ))}
        </div>
        <div
          style={{
            background: "var(--card)",
            border: "1px solid var(--line)",
            borderRadius: 14,
            overflow: "hidden",
            marginBottom: 16,
          }}
        >
          <div style={{ aspectRatio: "1", background: "#0d0d10", position: "relative" }}>
            <AuthenticatedImage
              src={item.img}
              alt="공유할 광고"
              style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
            />
            <span
              style={{
                position: "absolute",
                left: 11,
                top: 11,
                background: "rgba(0,0,0,.5)",
                color: "var(--ink-soft)",
                fontSize: 10,
                fontWeight: 700,
                padding: "4px 8px",
                borderRadius: 6,
              }}
            >
              AI 광고
            </span>
          </div>
          <div style={{ padding: "14px 16px" }}>
            <div
              style={{
                fontSize: 14,
                fontWeight: 700,
                fontFamily: "var(--serif)",
                fontStyle: "italic",
                marginBottom: 5,
              }}
            >
              {copy.head}
            </div>
            <div
              style={{
                fontSize: 12.5,
                lineHeight: 1.6,
                color: "var(--ink-soft)",
                marginBottom: 7,
                whiteSpace: "pre-line",
              }}
            >
              {copy.body}
            </div>
            <div style={{ fontSize: 12, color: "var(--gold)", fontWeight: 600 }}>
              {copy.tags}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
          <button
            style={{
              width: "100%",
              padding: 12,
              border: "none",
              borderRadius: 11,
              background: "var(--gold)",
              color: "#16151A",
              fontSize: 13,
              fontWeight: 700,
              cursor: "pointer",
            }}
            onClick={shareNow}
          >
            ↗ {PLATFORM_NAMES[platform] || platform} 공유
          </button>
        </div>
        {!s.isPremium && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "12px 14px",
              background: "rgba(242,169,59,.08)",
              border: "1px solid rgba(242,169,59,.24)",
              borderRadius: 11,
            }}
          >
            <span>🔒</span>
            <span
              style={{ flex: 1, fontSize: 12, color: "var(--gold-deep)", fontWeight: 600 }}
            >
              고해상도 원본 다운로드는 프리미엄
            </span>
            <button
              style={{
                padding: "8px 13px",
                border: "none",
                borderRadius: 9,
                background: "transparent",
                color: "var(--gold)",
                fontSize: 12,
                fontWeight: 800,
                cursor: "pointer",
              }}
              onClick={() => router.push("/billing")}
            >
              업그레이드 →
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

export default function SharePage() {
  return (
    <Suspense fallback={<div className="page">공유 정보를 확인하는 중입니다.</div>}>
      <ShareContent />
    </Suspense>
  );
}
