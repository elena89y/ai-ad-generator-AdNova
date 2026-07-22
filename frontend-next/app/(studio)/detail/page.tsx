"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  FORMAT_LABELS,
  apiFetch,
  formatAdType,
  getItemPlatformCopy,
  getToken,
  historyToCard,
  readApiError,
  readJsonSafely,
} from "@/lib/api";
import {
  deleteStoredAd,
  downloadHistoryResult,
  downloadImageUrl,
} from "@/lib/sns";
import { useStudio } from "@/components/studio/StudioProvider";
import { AuthenticatedImage } from "@/components/studio/AuthenticatedImage";

const TABS = [
  { p: "instagram", label: "IG" },
  { p: "facebook", label: "FB" },
  { p: "x", label: "X" },
  { p: "threads", label: "Threads" },
];

function AdNovaWatermark() {
  return (
    <div
      aria-label="AdNova 무료 버전 워터마크"
      style={{
        position: "absolute",
        right: "3%",
        bottom: "3%",
        zIndex: 3,
        width: "clamp(78px, 22%, 120px)",
        pointerEvents: "none",
        userSelect: "none",
      }}
    >
      <Image
        src="/brand/brand-logo.png"
        alt="AdNova"
        width={240}
        height={76}
        style={{
          display: "block",
          width: "100%",
          height: "auto",
          opacity: 0.82,
          filter: "drop-shadow(0 2px 4px rgba(0, 0, 0, 0.38))",
        }}
      />
    </div>
  );
}

function DetailContent() {
  const s = useStudio();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [platform, setPlatform] = useState("instagram");
  const [loading, setLoading] = useState(false);
  const [typographyOn, setTypographyOn] = useState(true);

  const requestedHistoryId = Number(searchParams.get("historyId"));

  const historyId =
    Number.isInteger(requestedHistoryId) && requestedHistoryId > 0
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
        const response = await apiFetch(`/api/history/${historyId}`);
        const data = await readJsonSafely(response);

        if (!response.ok) {
          throw new Error(
            readApiError(
              data,
              "광고 상세 정보를 불러오지 못했습니다.",
            ),
          );
        }

        if (!cancelled) {
          s.openDetail(
            historyToCard(
              data as Parameters<typeof historyToCard>[0],
            ),
          );
        }
      } catch (error) {
        if (!cancelled) {
          s.toast(
            error instanceof Error
              ? error.message
              : "광고 상세 정보를 불러오지 못했습니다.",
          );

          router.replace("/my-ads");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadDetail();

    return () => {
      cancelled = true;
    };
  }, [historyId, item?.historyId, router, s]);

  if (!s.ready || !s.token) {
    return (
      <div className="page">
        로그인 정보를 확인하는 중입니다.
      </div>
    );
  }

  if (!item) {
    return loading ? (
      <div className="page">
        광고 정보를 불러오는 중입니다.
      </div>
    ) : null;
  }

  const copy = getItemPlatformCopy(item, platform);

  const hasTypographyPair = Boolean(
    item.imageWithTypography &&
      item.imageWithoutTypography,
  );

  const detailImageSrc = hasTypographyPair
    ? typographyOn
      ? item.imageWithTypography
      : item.imageWithoutTypography
    : item.img;

  function openShare() {
    if (!item) return;

    const shareItem = hasTypographyPair
      ? {
          ...item,
          img: detailImageSrc || item.img,
          historyId: undefined,
        }
      : item;

    s.openShare(
      shareItem,
      historyId
        ? `/detail?historyId=${historyId}`
        : "/detail",
      platform,
    );

    router.push("/share");
  }

  async function downloadFormat(
    url: string,
    filename: string,
  ) {
    if (!s.isPremium) {
      router.push("/billing");
      return;
    }

    try {
      const token = getToken();

      const response = await fetch(url, {
        headers: token
          ? {
              Authorization: `Bearer ${token}`,
            }
          : {},
      });

      if (!response.ok) {
        throw new Error(
          "이미지를 불러오지 못했습니다.",
        );
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = objectUrl;
      link.download = filename;

      document.body.appendChild(link);
      link.click();
      link.remove();

      URL.revokeObjectURL(objectUrl);

      s.toast(
        "고해상도 원본이 다운로드되었습니다.",
      );
    } catch (error) {
      s.toast(
        error instanceof Error
          ? error.message
          : "광고 이미지를 다운로드하지 못했습니다.",
      );
    }
  }

  async function deleteAd() {
    if (
      !item ||
      !confirm("이 광고를 삭제할까요?")
    ) {
      return;
    }

    try {
      await deleteStoredAd(item.historyId);

      s.setAds(
        s.ads.filter((ad) => ad !== item),
      );

      s.refreshDashboardSummary();
      router.push("/my-ads");
      s.toast("광고를 삭제했습니다.");
    } catch (error) {
      s.toast(
        error instanceof Error
          ? error.message
          : "광고 삭제에 실패했습니다.",
      );
    }
  }

  return (
    <section>
      <div className="subbar">
        <Link
          href="/my-ads"
          className="back-link"
          style={{ margin: 0 }}
        >
          ← 내 광고
        </Link>

        <span
          style={{
            marginLeft: "auto",
            fontSize: 12,
            color: "var(--ink-mute)",
          }}
        >
          {item.date
            ? `${item.date} 생성`
            : ""}
        </span>
      </div>

      <div
        className="page"
        style={{ maxWidth: 820 }}
      >
        <div className="detail-layout">
          <div>
            <div
              style={{
                position: "relative",
                borderRadius: 14,
                overflow: "hidden",
              }}
            >
              <AuthenticatedImage
                src={detailImageSrc}
                alt="생성된 광고"
                style={{
                  display: "block",
                  width: "100%",
                  height: "auto",
                }}
              />

              <span
                style={{
                  position: "absolute",
                  left: 12,
                  top: 12,
                  zIndex: 2,
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

              {!s.isPremium && (
                <AdNovaWatermark />
              )}
            </div>

            {hasTypographyPair && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent:
                    "space-between",
                  marginTop: 12,
                  padding: "10px 13px",
                  border:
                    "1px solid var(--line)",
                  borderRadius: 10,
                  background: "#1d1c22",
                }}
              >
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 700,
                    color:
                      "var(--ink-soft)",
                  }}
                >
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
                    onChange={(event) =>
                      setTypographyOn(
                        event.target.checked,
                      )
                    }
                  />

                  {typographyOn
                    ? "포함"
                    : "타이포 없음"}
                </label>
              </div>
            )}

            <div className="detail-actions">
              <button
                className="oa"
                onClick={openShare}
              >
                ↗ 공유
              </button>

              {s.isPremium && (
                <button
                  className="oa download"
                  onClick={() =>
                    hasTypographyPair
                      ? downloadImageUrl(
                          detailImageSrc ||
                            item.img,
                          s.toast,
                        )
                      : downloadHistoryResult(
                          item.historyId,
                          s.toast,
                        )
                  }
                >
                  ⇩ 다운로드
                </button>
              )}

              <button
                className="oa delete"
                onClick={deleteAd}
              >
                삭제
              </button>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            <div>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: ".06em",
                  textTransform: "uppercase",
                  color:
                    "var(--ink-mute)",
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
                <div
                  style={{
                    display: "flex",
                    justifyContent:
                      "space-between",
                    gap: 16,
                  }}
                >
                  <span
                    style={{
                      color:
                        "var(--ink-mute)",
                    }}
                  >
                    상품명
                  </span>

                  <b
                    style={{
                      textAlign: "right",
                    }}
                  >
                    {item.productName ||
                      item.hl ||
                      "광고 상품"}
                  </b>
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent:
                      "space-between",
                  }}
                >
                  <span
                    style={{
                      color:
                        "var(--ink-mute)",
                    }}
                  >
                    스타일
                  </span>

                  <span
                    style={{
                      color: "var(--gold)",
                      fontWeight: 700,
                    }}
                  >
                    {item.style ||
                      "정보 없음"}
                  </span>
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent:
                      "space-between",
                  }}
                >
                  <span
                    style={{
                      color:
                        "var(--ink-mute)",
                    }}
                  >
                    형식
                  </span>

                  <span>
                    {formatAdType(
                      item.adType,
                    )}
                  </span>
                </div>
              </div>
            </div>

            <div
              style={{
                height: 1,
                background: "var(--line)",
              }}
            />

            <div style={{ flex: 1 }}>
              <div
                style={{
                  display: "flex",
                  gap: 4,
                  marginBottom: 11,
                }}
              >
                {TABS.map((tab) => (
                  <button
                    key={tab.p}
                    className={`shtab${
                      platform === tab.p
                        ? " on"
                        : ""
                    }`}
                    onClick={() =>
                      setPlatform(tab.p)
                    }
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div
                style={{
                  fontSize: 15,
                  fontWeight: 700,
                  fontFamily:
                    "var(--serif)",
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
                  color:
                    "var(--ink-soft)",
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
                  background:
                    "rgba(242,169,59,.08)",
                  border:
                    "1px solid rgba(242,169,59,.24)",
                  borderRadius: 11,
                }}
              >
                <span>🔒</span>

                <span
                  style={{
                    flex: 1,
                    fontSize: 11.5,
                    color:
                      "var(--gold-deep)",
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
                    background:
                      "var(--gold)",
                    color: "#16151A",
                    fontSize: 11.5,
                    fontWeight: 800,
                    cursor: "pointer",
                  }}
                  onClick={() =>
                    router.push("/billing")
                  }
                >
                  업그레이드
                </button>
              </div>
            )}
          </div>
        </div>

        {(item.formatOutputs?.length ??
          0) > 0 && (
          <div style={{ marginTop: 24 }}>
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: ".06em",
                textTransform: "uppercase",
                color: "var(--ink-mute)",
                marginBottom: 12,
              }}
            >
              {FORMAT_LABELS[
                item.purpose ?? ""
              ] || "결과"}

              {(item.formatOutputs
                ?.length ?? 0) > 1
                ? ` · ${item.formatOutputs!.length}개`
                : ""}
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(2,minmax(0,1fr))",
                gap: 12,
                alignItems: "start",
              }}
            >
              {item.formatOutputs!.map(
                (url, index) => {
                  const label =
                    FORMAT_LABELS[
                      item.purpose ?? ""
                    ] || "결과";

                  const alt =
                    item.formatOutputs!
                      .length > 1
                      ? `${label} ${index + 1}`
                      : label;

                  return (
                    <div
                      key={`${url}-${index}`}
                      style={{
                        position: "relative",
                        overflow: "hidden",
                        border:
                          "1px solid var(--line)",
                        borderRadius: 12,
                      }}
                    >
                      <AuthenticatedImage
                        src={url}
                        alt={alt}
                        style={{
                          display: "block",
                          width: "100%",
                          height: "auto",
                        }}
                      />

                      {!s.isPremium && (
                        <AdNovaWatermark />
                      )}

                      <button
                        type="button"
                        className="oa download"
                        style={{
                          position:
                            "absolute",
                          left: 10,
                          bottom: 10,
                          zIndex: 4,
                          background:
                            "rgba(22,21,26,.88)",
                        }}
                        onClick={() =>
                          downloadFormat(
                            url,
                            `adnova-${
                              item.purpose ||
                              "format"
                            }-${index + 1}.jpg`,
                          )
                        }
                      >
                        다운로드
                      </button>
                    </div>
                  );
                },
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default function DetailPage() {
  return (
    <Suspense
      fallback={
        <div className="page">
          광고 상세 정보를 불러오는 중입니다.
        </div>
      }
    >
      <DetailContent />
    </Suspense>
  );
}