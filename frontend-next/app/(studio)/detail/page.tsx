"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import {
  FORMAT_LABELS,
  apiFetch,
  formatAdType,
  formatSizeBadge,
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
  exportSnsPost,
} from "@/lib/sns";
import { useStudio } from "@/components/studio/StudioProvider";
import { AuthenticatedImage } from "@/components/studio/AuthenticatedImage";

const TABS = [
  { p: "instagram", label: "IG" },
  { p: "facebook", label: "FB" },
  { p: "x", label: "X" },
  { p: "threads", label: "Threads" },
];

const SHARE_GUIDES: Record<string, string> = {
  instagram:
    "이미지는 Instagram 게시물에 자동으로 첨부돼요.\n게시글 문구는 자동 입력되지 않으므로 캡션란에 붙여넣어 주세요.",
  facebook:
    "이미지는 Facebook 게시물에 자동으로 첨부돼요.\n게시글 문구는 자동 입력되지 않을 수 있으므로 게시물 작성란에 붙여넣어 주세요.",
  x:
    "이미지와 문구가 X 작성 화면에 함께 전달돼요.\n기기나 앱 환경에 따라 문구가 보이지 않으면 문구 복사를 이용해 주세요.",
  threads:
    "이미지와 문구가 Threads 작성 화면에 함께 전달돼요.\n기기나 앱 환경에 따라 문구가 보이지 않으면 문구 복사를 이용해 주세요.",
};

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
  const [shareModalOpen, setShareModalOpen] = useState(false);
  const [reportModalOpen, setReportModalOpen] = useState(false);
  const [reportCategory, setReportCategory] = useState("result_quality");
  const [reportContent, setReportContent] = useState("");
  const [reportSubmitting, setReportSubmitting] = useState(false);

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

  useEffect(() => {
    if (!shareModalOpen && !reportModalOpen) return;

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setShareModalOpen(false);
        setReportModalOpen(false);
      }
    }

    document.addEventListener("keydown", closeOnEscape);

    return () => {
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [shareModalOpen, reportModalOpen]);

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

  // 타이포 토글은 '타이포 포함/없음' 두 이미지가 실제로 다를 때만 의미가 있다.
  // 템플릿은 타이포가 이미 구워진 단일본(with==without 같은 URL)이라 선택 불가 → 토글 숨김.
  const hasTypographyPair = Boolean(
    item.imageWithTypography &&
      item.imageWithoutTypography &&
      item.imageWithTypography !== item.imageWithoutTypography,
  );

  const detailImageSrc = hasTypographyPair
    ? typographyOn
      ? item.imageWithTypography
      : item.imageWithoutTypography
    : item.img;

  function openShare() {
    setShareModalOpen(true);
  }

  async function copyShareText() {
    const shareText = [copy.head, copy.body, copy.tags]
      .filter(Boolean)
      .join("\n\n");

    try {
      await navigator.clipboard.writeText(shareText);
      s.toast("게시글 문구를 복사했어요.");
    } catch {
      s.toast("문구를 복사하지 못했습니다. 문구를 직접 선택해 복사해 주세요.");
    }
  }

  async function shareCurrentPlatform() {
    if (!item) {
      s.toast("공유할 광고 정보를 찾을 수 없습니다.");
      return;
    }

    const shareItem = hasTypographyPair
      ? {
          ...item,
          img: detailImageSrc || item.img,
          historyId: undefined,
        }
      : item;

    try {
      await exportSnsPost(
        platform,
        {
          ...shareItem,
          copyHead: copy.head,
          copyBody: copy.body,
          copyTags: copy.tags,
        },
        s.toast,
      );
    } catch (error) {
      s.toast(
        error instanceof Error
          ? error.message
          : "SNS 공유를 실행하지 못했습니다.",
      );
    }
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

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!item?.advertisementId) {
      s.toast("신고할 광고 정보를 찾을 수 없습니다.");
      return;
    }

    if (!reportContent.trim()) {
      s.toast("신고 사유를 입력해 주세요.");
      return;
    }

    setReportSubmitting(true);
    try {
      const response = await apiFetch("/api/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category: reportCategory,
          title: `${item.productName || item.hl || "광고"} 생성 결과 신고`,
          content: reportContent.trim(),
          advertisement_id: item.advertisementId,
        }),
      });
      const data = await readJsonSafely(response);

      if (!response.ok) {
        throw new Error(readApiError(data, "신고를 등록하지 못했습니다."));
      }

      setReportContent("");
      setReportCategory("result_quality");
      setReportModalOpen(false);
      s.toast("신고가 접수되었습니다. 고객센터에서 진행 상태를 확인할 수 있어요.");
    } catch (error) {
      s.toast(
        error instanceof Error ? error.message : "신고를 등록하지 못했습니다.",
      );
    } finally {
      setReportSubmitting(false);
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
                type="button"
                className="oa"
                onClick={openShare}
              >
                ⤴ 공유
              </button>

              {s.isPremium && (
                <button
                  type="button"
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
                type="button"
                className="oa delete"
                onClick={deleteAd}
              >
                삭제
              </button>

              {item.advertisementId && (
                <button
                  type="button"
                  className="oa"
                  onClick={() => setReportModalOpen(true)}
                >
                  신고하기
                </button>
              )}
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

                      {formatSizeBadge(url) && (
                        <span
                          style={{
                            position: "absolute",
                            top: 8,
                            left: 8,
                            padding: "3px 8px",
                            borderRadius: 6,
                            background: "rgba(0,0,0,0.62)",
                            color: "#fff",
                            fontSize: 12,
                            fontWeight: 600,
                            letterSpacing: "0.02em",
                            pointerEvents: "none",
                            zIndex: 5,
                          }}
                        >
                          {formatSizeBadge(url)}
                        </span>
                      )}

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


      {reportModalOpen && (
        <div
          role="presentation"
          onClick={() => setReportModalOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
            background: "rgba(0, 0, 0, 0.68)",
            backdropFilter: "blur(6px)",
          }}
        >
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-modal-title"
            onClick={(event) => event.stopPropagation()}
            onSubmit={(event) => void submitReport(event)}
            style={{
              width: "min(100%, 480px)",
              padding: 22,
              border: "1px solid var(--line)",
              borderRadius: 18,
              background: "#1d1c22",
              boxShadow: "0 24px 70px rgba(0, 0, 0, 0.55)",
            }}
          >
            <div style={{ display: "flex", alignItems: "start", justifyContent: "space-between", gap: 16 }}>
              <div>
                <h3 id="report-modal-title" style={{ margin: 0, fontSize: 19 }}>
                  광고 신고하기
                </h3>
                <p style={{ margin: "6px 0 0", color: "var(--ink-mute)", fontSize: 12, lineHeight: 1.6 }}>
                  생성 결과에서 확인이 필요한 내용을 알려 주세요.
                </p>
              </div>
              <button
                type="button"
                aria-label="신고창 닫기"
                onClick={() => setReportModalOpen(false)}
                style={{ width: 34, height: 34, border: "1px solid var(--line)", borderRadius: 9, background: "transparent", color: "var(--ink-soft)", fontSize: 19, cursor: "pointer" }}
              >
                ×
              </button>
            </div>

            <label style={{ display: "grid", gap: 7, marginTop: 18, fontSize: 12, fontWeight: 700 }}>
              신고 사유
              <select
                value={reportCategory}
                onChange={(event) => setReportCategory(event.target.value)}
                style={{ height: 42, border: "1px solid var(--line)", borderRadius: 9, background: "#18171c", color: "var(--ink)", padding: "0 11px" }}
              >
                <option value="result_quality">생성 결과 품질</option>
                <option value="copyright">저작권 또는 상표 관련</option>
                <option value="policy">부적절한 내용</option>
                <option value="other">기타</option>
              </select>
            </label>

            <label style={{ display: "grid", gap: 7, marginTop: 14, fontSize: 12, fontWeight: 700 }}>
              상세 내용
              <textarea
                value={reportContent}
                maxLength={5000}
                onChange={(event) => setReportContent(event.target.value)}
                placeholder="확인이 필요한 내용을 자세히 적어 주세요."
                style={{ minHeight: 130, resize: "vertical", border: "1px solid var(--line)", borderRadius: 9, background: "#18171c", color: "var(--ink)", padding: 11, lineHeight: 1.55 }}
              />
            </label>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 9, marginTop: 18 }}>
              <button type="button" className="oa" onClick={() => setReportModalOpen(false)}>
                취소
              </button>
              <button type="submit" className="oa download" disabled={reportSubmitting}>
                {reportSubmitting ? "접수 중..." : "신고 접수"}
              </button>
            </div>
          </form>
        </div>
      )}

      {shareModalOpen && (
        <div
          role="presentation"
          onClick={() => setShareModalOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
            background: "rgba(0, 0, 0, 0.68)",
            backdropFilter: "blur(6px)",
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="share-modal-title"
            onClick={(event) => event.stopPropagation()}
            style={{
              width: "min(100%, 480px)",
              maxHeight: "calc(100vh - 40px)",
              overflowY: "auto",
              padding: 22,
              border: "1px solid var(--line)",
              borderRadius: 18,
              background: "#1d1c22",
              boxShadow: "0 24px 70px rgba(0, 0, 0, 0.55)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 16,
                marginBottom: 18,
              }}
            >
              <div>
                <h3
                  id="share-modal-title"
                  style={{
                    margin: 0,
                    fontSize: 19,
                  }}
                >
                  SNS에 공유하기
                </h3>

                <p
                  style={{
                    margin: "6px 0 0",
                    fontSize: 12,
                    color: "var(--ink-mute)",
                  }}
                >
                  공유할 플랫폼과 문구를 확인하세요.
                </p>
              </div>

              <button
                type="button"
                aria-label="공유창 닫기"
                onClick={() => setShareModalOpen(false)}
                style={{
                  width: 34,
                  height: 34,
                  border: "1px solid var(--line)",
                  borderRadius: 9,
                  background: "transparent",
                  color: "var(--ink-soft)",
                  fontSize: 19,
                  cursor: "pointer",
                }}
              >
                ×
              </button>
            </div>

            <div
              style={{
                display: "flex",
                gap: 6,
                marginBottom: 16,
              }}
            >
              {TABS.map((tab) => (
                <button
                  key={tab.p}
                  type="button"
                  className={`shtab${
                    platform === tab.p ? " on" : ""
                  }`}
                  onClick={() => setPlatform(tab.p)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div
              style={{
                marginBottom: 14,
                padding: "11px 13px",
                border: "1px solid rgba(139, 92, 246, 0.3)",
                borderRadius: 11,
                background: "rgba(139, 92, 246, 0.09)",
                fontSize: 12,
                lineHeight: 1.6,
                color: "var(--ink-soft)",
                whiteSpace: "pre-line",
              }}
            >
              💡 {SHARE_GUIDES[platform]}
            </div>

            <div
              style={{
                position: "relative",
                overflow: "hidden",
                marginBottom: 16,
                border: "1px solid var(--line)",
                borderRadius: 12,
                background: "#16151a",
              }}
            >
              <AuthenticatedImage
                src={detailImageSrc}
                alt="공유할 광고 이미지"
                style={{
                  display: "block",
                  width: "100%",
                  maxHeight: 260,
                  objectFit: "contain",
                }}
              />

              {!s.isPremium && <AdNovaWatermark />}
            </div>

            <div
              style={{
                padding: 15,
                border: "1px solid var(--line)",
                borderRadius: 12,
                background: "#18171c",
              }}
            >
              <div
                style={{
                  marginBottom: 8,
                  fontSize: 15,
                  fontWeight: 700,
                  fontFamily: "var(--serif)",
                  fontStyle: "italic",
                }}
              >
                {copy.head}
              </div>

              <div
                style={{
                  fontSize: 12.5,
                  lineHeight: 1.65,
                  color: "var(--ink-soft)",
                  whiteSpace: "pre-line",
                }}
              >
                {copy.body}
              </div>

              {copy.tags && (
                <div
                  style={{
                    marginTop: 9,
                    fontSize: 11.5,
                    fontWeight: 600,
                    color: "var(--gold)",
                    whiteSpace: "pre-line",
                  }}
                >
                  {copy.tags}
                </div>
              )}
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 9,
                marginTop: 18,
              }}
            >
              <button
                type="button"
                className="oa"
                onClick={() => setShareModalOpen(false)}
              >
                취소
              </button>

              <button
                type="button"
                className="oa"
                onClick={() => void copyShareText()}
              >
                📋 문구 복사
              </button>

              <button
                type="button"
                className="oa download"
                onClick={() => void shareCurrentPlatform()}
              >
                {platform === "instagram"
                  ? "⤴ Instagram으로 공유"
                  : platform === "facebook"
                    ? "⤴ Facebook으로 공유"
                    : platform === "x"
                      ? "⤴ X로 공유"
                      : "⤴ Threads로 공유"}
              </button>
            </div>
          </div>
        </div>
      )}

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
