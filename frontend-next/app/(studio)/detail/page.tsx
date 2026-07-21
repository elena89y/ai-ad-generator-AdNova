"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  apiFetch,
  formatAdType,
  getItemPlatformCopy,
  historyToCard,
  readApiError,
  readJsonSafely,
} from "@/lib/api";
import { deleteStoredAd, downloadHistoryResult, downloadImageUrl } from "@/lib/sns";
import { useStudio } from "@/components/studio/StudioProvider";
import { AuthenticatedImage } from "@/components/studio/AuthenticatedImage";

const TABS = [
  { p: "instagram", label: "IG" },
  { p: "facebook", label: "FB" },
  { p: "x", label: "X" },
  { p: "threads", label: "Threads" },
];

function DetailContent() {
  const s = useStudio();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [platform, setPlatform] = useState("instagram");
  const [loading, setLoading] = useState(false);
  // [html-parity] 상세 화면 타이포 토글 — html #detailTypographyToggle 이식 (Next 이관 시 누락)
  const [typographyOn, setTypographyOn] = useState(true);
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
      router.replace("/my-ads");
      return;
    }
    if (!historyId || item?.historyId === historyId) return;

    let cancelled = false;
    setLoading(true);

    async function loadDetail() {
      try {
        const res = await apiFetch(`/api/history/${historyId}`);
        const data = await readJsonSafely(res);
        if (!res.ok) {
          throw new Error(readApiError(data, "광고 상세 정보를 불러오지 못했습니다"));
        }
        if (!cancelled) s.openDetail(historyToCard(data as Parameters<typeof historyToCard>[0]));
      } catch (err) {
        if (!cancelled) {
          s.toast(err instanceof Error ? err.message : "광고 상세 정보를 불러오지 못했습니다");
          router.replace("/my-ads");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadDetail();
    return () => {
      cancelled = true;
    };
  }, [historyId, item?.historyId, router, s]);

  if (!s.ready || !s.token) {
    return <div className="page">로그인 정보를 확인하는 중입니다.</div>;
  }
  if (!item) return loading ? <div className="page">광고 정보를 불러오는 중입니다.</div> : null;
  const copy = getItemPlatformCopy(item, platform);
  // [html-parity] 페어가 모두 있을 때만 토글 노출, 없으면 item.img 폴백 (html getDetailImageUrl 이식)
  const hasTypographyPair = Boolean(item.imageWithTypography && item.imageWithoutTypography);
  const detailImageSrc = hasTypographyPair
    ? (typographyOn ? item.imageWithTypography : item.imageWithoutTypography)
    : item.img;

  function openShare() {
    if (!item) return;
    // 타이포 토글 상태를 공유 대상 이미지에 반영
    // (historyId를 제거해야 sns.ts가 저장본 다운로드 API 대신 이 URL을 직접 사용)
    const shareItem = hasTypographyPair
      ? { ...item, img: detailImageSrc || item.img, historyId: undefined }
      : item;
    s.openShare(shareItem, historyId ? `/detail?historyId=${historyId}` : "/detail", platform);
    router.push("/share");
  }

  async function deleteAd() {
    if (!item || !confirm("이 광고를 삭제할까요?")) return;
    try {
      await deleteStoredAd(item.historyId);
      s.setAds(s.ads.filter((a) => a !== item));
      s.refreshDashboardSummary();
      router.push("/my-ads");
      s.toast("광고를 삭제했어요");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "광고 삭제에 실패했습니다");
    }
  }

  return (
    <section>
      <div className="subbar">
        <Link href="/my-ads" className="back-link" style={{ margin: 0 }}>
          ← 내 광고
        </Link>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--ink-mute)" }}>
          {item.date ? `${item.date} 생성` : ""}
        </span>
      </div>
      <div className="page" style={{ maxWidth: 820 }}>
        <div className="detail-layout">
          <div>
            <div
              style={{
                position: "relative",
                aspectRatio: "4/5",
                borderRadius: 14,
                overflow: "hidden",
                background: "#0d0d10",
              }}
            >
              <AuthenticatedImage
                src={detailImageSrc}
                alt="생성된 광고"
                style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
              />
              <span
                style={{
                  position: "absolute",
                  left: 12,
                  top: 12,
                  background: "var(--gold)",
                  color: "#16151A",
                  fontSize: 10,
                  fontWeight: 800,
                  padding: "4px 9px",
                  borderRadius: 6,
                }}
              >
                AI 생성
              </span>
            </div>
            {/* [html-parity] 타이포 토글 — html #detailTypographyOption 이식 (Next 이관 시 누락) */}
            {hasTypographyPair && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginTop: 12,
                  padding: "10px 13px",
                  border: "1px solid var(--line)",
                  borderRadius: 10,
                  background: "#1d1c22",
                }}
              >
                <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-soft)" }}>
                  타이포
                </span>
                <label
                  htmlFor="detailTypographyToggle"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 7,
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  <input
                    id="detailTypographyToggle"
                    type="checkbox"
                    checked={typographyOn}
                    onChange={(e) => setTypographyOn(e.target.checked)}
                  />
                  {typographyOn ? "포함" : "무타이포"}
                </label>
              </div>
            )}
            <div className="detail-actions">
              <button className="oa" onClick={openShare}>
                ↗ 공유
              </button>
              {s.isPremium && (
                <button
                  className="oa download"
                  onClick={() =>
                    hasTypographyPair
                      ? downloadImageUrl(detailImageSrc || item.img, s.toast)
                      : downloadHistoryResult(item.historyId, s.toast)
                  }
                >
                  ⬇ 다운로드
                </button>
              )}
              <button className="oa delete" onClick={deleteAd}>
                삭제
              </button>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: ".06em",
                  textTransform: "uppercase",
                  color: "var(--ink-mute)",
                  marginBottom: 10,
                }}
              >
                정보
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 9,
                  fontSize: 12.5,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
                  <span style={{ color: "var(--ink-mute)" }}>상품명</span>
                  <b style={{ textAlign: "right" }}>
                    {item.productName || item.hl || "광고 상품"}
                  </b>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--ink-mute)" }}>스타일</span>
                  <span style={{ color: "var(--gold)", fontWeight: 700 }}>
                    {item.style || "정보 없음"}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--ink-mute)" }}>형식</span>
                  <span>{formatAdType(item.adType)}</span>
                </div>
              </div>
            </div>
            <div style={{ height: 1, background: "var(--line)" }} />
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", gap: 4, marginBottom: 11 }}>
                {TABS.map((t) => (
                  <button
                    key={t.p}
                    className={`shtab${platform === t.p ? " on" : ""}`}
                    onClick={() => setPlatform(t.p)}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  fontFamily: "var(--serif)",
                  fontStyle: "italic",
                  marginBottom: 7,
                }}
              >
                {copy.head}
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  lineHeight: 1.6,
                  color: "var(--ink-soft)",
                  whiteSpace: "pre-line",
                }}
              >
                {copy.body}
              </div>
              <div
                style={{
                  fontSize: 11.5,
                  color: "var(--gold)",
                  marginTop: 8,
                  fontWeight: 600,
                }}
              >
                {copy.tags}
              </div>
            </div>
            {!s.isPremium && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "11px 13px",
                  background: "rgba(242,169,59,.08)",
                  border: "1px solid rgba(242,169,59,.24)",
                  borderRadius: 11,
                }}
              >
                <span>🔒</span>
                <span
                  style={{
                    flex: 1,
                    fontSize: 11.5,
                    color: "var(--gold-deep)",
                    fontWeight: 600,
                  }}
                >
                  원본 다운로드는 프리미엄
                </span>
                <button
                  style={{
                    padding: "7px 12px",
                    border: "none",
                    borderRadius: 9,
                    background: "var(--gold)",
                    color: "#16151A",
                    fontSize: 11.5,
                    fontWeight: 800,
                    cursor: "pointer",
                  }}
                  onClick={() => router.push("/billing")}
                >
                  업그레이드
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export default function DetailPage() {
  return (
    <Suspense fallback={<div className="page">광고 상세 정보를 불러오는 중입니다.</div>}>
      <DetailContent />
    </Suspense>
  );
}
