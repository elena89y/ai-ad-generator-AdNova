"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ALLOWED_IMAGE_TYPES,
  AdItem,
  GenerateResult,
  PlatformCopy,
  STYLE_PRESET_MAP,
  apiFetch,
  formatDateLabel,
  getToken,
  normalizePlatformCopy,
  readApiError,
  readJsonSafely,
  splitCopyText,
  toAbsoluteUrl,
  toStyleLabel,
} from "@/lib/api";
import { useStudio } from "@/components/studio/StudioProvider";
import { AppBar } from "@/components/studio/chrome";
import { AuthenticatedImage } from "@/components/studio/AuthenticatedImage";
import { TemplateGrid } from "@/components/studio/TemplateGrid";

const GEN_STEPS = [
  "사진을 분석하는 중…",
  "스타일을 입히는 중…",
  "광고 문구를 쓰는 중…",
  "마무리하는 중…",
];

const STYLES: { label: string; sw: string }[] = [
  { label: "웜 빈티지", sw: "linear-gradient(135deg,#F2A93B,#C42E5C)" },
  { label: "모노톤", sw: "linear-gradient(135deg,#e8e6ea,#9a95a5)" },
  { label: "팝 비비드", sw: "linear-gradient(135deg,#5BC0EB,#C42E5C)" },
  { label: "에디토리얼", sw: "linear-gradient(135deg,#17151C,#8A7C9A)" },
  { label: "리얼리즘", sw: "linear-gradient(135deg,#6B8F71,#D8C8A8)" },
  { label: "파스텔", sw: "linear-gradient(135deg,#F6D8E4,#D9F0E6)" },
];

const USES = [
  { v: "sns", label: "SNS" },
  { v: "card", label: "카드뉴스" },
  { v: "banner", label: "배너" },
  { v: "flyer", label: "전단지" },
];

/* 템플릿 formats[0] → 용도 버튼 매핑 (v6 T4; detail_page 는 용도 버튼 없음 → 유지) */
const FORMAT_TO_USE: Record<string, string> = {
  sns: "sns",
  cardnews: "card",
  banner: "banner",
};

const PLATFORMS = [
  { p: "instagram", si: "ig", label: "Instagram", short: "IG" },
  { p: "facebook", si: "fb", label: "Facebook", short: "f" },
  { p: "x", si: "x", label: "X", short: "X" },
  { p: "threads", si: "th", label: "Threads", short: "@" },
];

/* 상품명 → 광고 유형 자동 감지 (프로토타입 detectMode 포팅) */
function detectModeText(name: string): string {
  const n = (name || "").trim();
  const cafe =
    /(라떼|밀크티|커피|아메리카노|스무디|에이드|주스|쿠키|스콘|케이크|음료|티\b)/;
  const obj =
    /(마우스|키보드|컵|잔|텀블러|화장품|케이스|가방|시계|이어폰|스탠드|괄사|기기|용품)/;
  if (!n) return "상품명을 입력하면 광고 유형을 자동 판단해요";
  if (obj.test(n)) return "사물·제품으로 인식 · 스튜디오 배경 모드";
  if (cafe.test(n)) return "카페 음료로 인식 · 배경 연출 모드";
  return "음식으로 인식 · 정체성 보존 향상 모드";
}

export default function StudioPage() {
  const s = useStudio();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [loadStep, setLoadStep] = useState(GEN_STEPS[0]);
  const [activePlatform, setActivePlatform] = useState("instagram");
  const [typographyOn, setTypographyOn] = useState(true);
  const [uploadInfo, setUploadInfo] = useState(
    "사진만 넣으면 배경·구도는 AI가 알아서 잡아줘요."
  );
  const stepTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (s.ready && !s.token) router.replace("/login");
  }, [s.ready, s.token, router]);

  useEffect(() => {
    s.refreshDashboardSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const platformCopy: PlatformCopy | null = s.currentResult
    ? currentCopyFor(activePlatform, s.currentResult)
    : null;

  function currentCopyFor(platform: string, result: GenerateResult): PlatformCopy {
    const copy = splitCopyText(result.copy_text);
    const fallback: PlatformCopy = {
      head: copy.head,
      body: copy.body,
      tags: `#AI광고 #AdNova #${toStyleLabel(result.style)}`,
    };
    return normalizePlatformCopy(result.platform_copies?.[platform], fallback);
  }

  function selectProductImage() {
    if (!getToken()) {
      s.toast("로그인 후 이미지를 업로드해 주세요");
      router.push("/login");
      return;
    }
    fileRef.current?.click();
  }

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    const MAX_IMAGE_SIZE = 5 * 1024 * 1024;
    if (!file) return;
    if (file.size > MAX_IMAGE_SIZE) {
      s.toast("이미지는 최대 5MB까지 업로드할 수 있습니다.");
      e.target.value = "";
    return;
    }
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      s.toast("jpg, png, webp 이미지만 업로드할 수 있습니다");
      e.target.value = "";
      return;
    }
    const formData = new FormData();
    formData.append("file", file);
    try {
      s.toast("이미지를 업로드하는 중입니다");
      const res = await apiFetch("/api/images/upload", { method: "POST", body: formData });
      const data = (await readJsonSafely(res)) as {
        image_id?: number;
        image_url?: string;
        filename?: string;
      } | null;
      if (!res.ok || !data)
        throw new Error(readApiError(data, "이미지 업로드에 실패했습니다"));
      s.setDashboardState({
        selectedImageId: data.image_id ?? null,
        selectedImageUrl: data.image_url ?? null,
        selectedImagePreview: URL.createObjectURL(file),
      });
      setUploadInfo(`업로드 완료: ${data.filename || file.name}`);
      s.toast("이미지가 업로드되었습니다");
    } catch (err) {
      s.setDashboardState({ selectedImageId: null, selectedImageUrl: null });
      s.toast(err instanceof Error ? err.message : "이미지 업로드에 실패했습니다");
    } finally {
      e.target.value = "";
    }
  }

  function startLoadingSteps() {
    let i = 0;
    setLoadStep(GEN_STEPS[0]);
    stepTimer.current = setInterval(() => {
      i++;
      if (i < GEN_STEPS.length) setLoadStep(GEN_STEPS[i]);
    }, 900);
  }
  function stopLoadingSteps() {
    if (stepTimer.current) clearInterval(stepTimer.current);
  }

  async function generate() {
    if (!s.isPremium && s.freeLeft <= 0) {
      s.setUpgradeOpen(true);
      return;
    }
    if (!getToken()) {
      s.toast("로그인 후 광고를 생성해 주세요");
      router.push("/login");
      return;
    }
    if (!s.selectedImageId) {
      s.toast("먼저 제품 사진을 업로드해 주세요");
      return;
    }
    const productName = s.prodName.trim();
    if (!productName) {
      s.toast("상품명을 입력해 주세요");
      return;
    }

    setLoading(true);
    startLoadingSteps();
    const formData = new FormData();
    formData.append("image_id", String(s.selectedImageId));
    formData.append("product_name", productName);
    formData.append("product_description", s.promptText.trim());
    formData.append("style", STYLE_PRESET_MAP[s.styleLabel] || "pop");
    formData.append("use_vision", "false");
    formData.append("poster", "false");

    try {
      const res = await apiFetch("/api/ads/generate", { method: "POST", body: formData });
      const data = (await readJsonSafely(res)) as GenerateResult | null;
      if (!res.ok || !data)
        throw new Error(readApiError(data, "광고 생성에 실패했습니다"));
      s.setDashboardState({ currentResult: data });
      s.refreshBilling(false);
      s.refreshDashboardSummary();
      s.refreshHistory(false);
      s.toast("광고가 생성되었습니다");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "광고 생성에 실패했습니다");
    } finally {
      stopLoadingSteps();
      setLoading(false);
    }
  }

  async function regenerate() {
    if (!s.isPremium && s.freeLeft <= 0) {
      s.setUpgradeOpen(true);
      return;
    }
    if (!s.currentResult?.asset_id) {
      s.toast("먼저 광고를 생성해 주세요");
      return;
    }
    const productName = s.prodName.trim();
    if (!productName) {
      s.toast("상품명을 입력해 주세요");
      return;
    }
    setLoading(true);
    startLoadingSteps();
    try {
      const res = await apiFetch("/api/ads/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          asset_id: s.currentResult.asset_id,
          style: STYLE_PRESET_MAP[s.styleLabel] || "pop",
          product_name: productName,
          product_description: s.promptText.trim(),
          prev_seed: s.currentResult.seed,
          use_vision: false,
          poster: false,
        }),
      });
      const data = (await readJsonSafely(res)) as GenerateResult | null;
      if (!res.ok || !data)
        throw new Error(readApiError(data, "다시 생성에 실패했습니다"));
      s.setDashboardState({ currentResult: data });
      s.refreshBilling(false);
      s.refreshDashboardSummary();
      s.refreshHistory(false);
      s.toast("광고를 다시 생성했습니다");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "다시 생성에 실패했습니다");
    } finally {
      stopLoadingSteps();
      setLoading(false);
    }
  }

  function buildCurrentOutputItem(): AdItem | null {
    if (!s.currentResult) return null;
    const productName = s.prodName.trim() || "광고 상품";
    const copy = currentCopyFor(activePlatform, s.currentResult);
    return {
      emoji: "✦",
      hl: copy.head || productName,
      copyHead: copy.head || productName,
      copyBody: copy.body || s.currentResult.copy_text || "",
      copyTags: copy.tags || "",
      platformCopies: s.currentResult.platform_copies || {},
      style: toStyleLabel(s.currentResult.style),
      rawStyle: s.currentResult.style,
      img: toAbsoluteUrl(resultImageUrl(s.currentResult)),
      inputImg: toAbsoluteUrl(s.selectedImageUrl),
      assetId: s.currentResult.asset_id,
      seed: s.currentResult.seed,
      adType: s.currentResult.poster ? "poster" : "image",
      date: formatDateLabel(new Date().toISOString()),
      productName,
      g: "linear-gradient(150deg,#2C2140,#8A3A5A 55%,#E0912F)",
      prod: "linear-gradient(160deg,#fff6e6,#f4c988)",
    };
  }

  function shareCurrentResult() {
    const item = buildCurrentOutputItem();
    if (!item) {
      s.toast("먼저 광고를 생성해 주세요");
      return;
    }
    s.openShare(item, "/studio", activePlatform);
    router.push("/share");
  }

  async function downloadResult() {
    if (!s.isPremium) {
      router.push("/billing");
      return;
    }
    const url = toAbsoluteUrl(resultImageUrl(s.currentResult));
    if (!url) {
      s.toast("다운로드할 광고 이미지가 없습니다");
      return;
    }
    try {
      const res = await fetch(url, {
        headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
      });
      if (!res.ok) throw new Error("이미지를 불러오지 못했습니다");
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = "adnova-ad.png";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      s.toast("고해상도 원본을 다운로드했어요");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "광고 이미지를 다운로드하지 못했습니다");
    }
  }

  const result = s.currentResult;
  // 타이포 페어(포함/무타이포)가 모두 있을 때만 토글 노출. 없으면 image_url 폴백.
  const hasTypographyPair = Boolean(
    result?.image_with_typography_url && result?.image_without_typography_url,
  );
  const resultImageUrl = (r: GenerateResult | null, on = typographyOn) => {
    if (!r) return undefined;
    return on
      ? r.image_with_typography_url || r.image_url
      : r.image_without_typography_url || r.image_url;
  };
  const beforeSrc =
    s.selectedImagePreview ??
    toAbsoluteUrl(s.selectedImageUrl) ??
    "";

  return (
    <section>
      <AppBar />
      <div className="dashboard-layout">
        {/* CONTROL RAIL */}
        <div className="control-rail">
          <div>
            <div className="rail-label">01 · 재료</div>
            <div
              style={{
                position: "relative",
                height: 150,
                borderRadius: 12,
                overflow: "hidden",
                border: beforeSrc
                  ? "1px solid var(--line)"
                  : "1px dashed rgba(255,255,255,.2)",
                background: beforeSrc
                  ? "var(--card)"
                  : "rgba(255,255,255,.025)",
                cursor: "pointer",
                transition: "border-color .2s ease, background .2s ease",
              }}
              onClick={selectProductImage}
            >
              {beforeSrc ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={beforeSrc}
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      display: "block",
                    }}
                    alt="제품 사진"
                  />

                  <span
                    style={{
                      position: "absolute",
                      top: 8,
                      right: 8,
                      background: "rgba(0,0,0,.65)",
                      color: "#fff",
                      fontSize: 11,
                      fontWeight: 700,
                      padding: "5px 10px",
                      borderRadius: 8,
                      backdropFilter: "blur(6px)",
                    }}
                  >
                    사진 바꾸기
                  </span>
                </>
              ) : (
                <div
                  style={{
                    width: "100%",
                    height: "100%",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 7,
                    textAlign: "center",
                    padding: 16,
                  }}
                >
                  <div
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: 11,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      background: "rgba(255,255,255,.06)",
                      border: "1px solid rgba(255,255,255,.08)",
                      fontSize: 18,
                    }}
                  >
                    📷
                  </div>

                  <div
                    style={{
                      color: "var(--ink)",
                      fontSize: 13,
                      fontWeight: 700,
                    }}
                  >
                    제품 사진 업로드
                  </div>

                  <div
                    style={{
                      color: "var(--ink-mute)",
                      fontSize: 11,
                      lineHeight: 1.4,
                    }}
                  >
                    클릭하여 이미지를 선택하세요
                  </div>
                </div>
              )}
            </div>
            <div
              style={{
                fontSize: 11,
                color: "var(--ink-mute)",
                marginTop: 8,
                lineHeight: 1.5,
              }}
            >
              {uploadInfo}
            </div>
            <label className="mini-label">
              상품명 <span className="hint">· 입력하면 분위기를 자동으로</span>
            </label>
            <input
              className="rail-input"
              placeholder="예: 카페 라떼, 흑당 밀크티"
              value={s.prodName}
              onChange={(e) => s.setDashboardState({ prodName: e.target.value })}
            />
            <div className="auto-mode" style={{ margin: "9px 0 0" }}>
              <span className="lamp" />
              <span>{detectModeText(s.prodName)}</span>
            </div>
            <label className="mini-label">
              추가 요청 <span className="hint">· 선택</span>
            </label>
            <textarea
              className="rail-textarea"
              placeholder="예: 시원한 여름 느낌 강조, 20대 타깃"
              value={s.promptText}
              onChange={(e) => s.setDashboardState({ promptText: e.target.value })}
            />
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
              {["할인 이벤트 강조", "신메뉴 출시", "인스타 감성"].map((tip) => (
                <span
                  key={tip}
                  className="chip-tip"
                  onClick={() =>
                    s.setDashboardState({
                      promptText: (s.promptText.trim() + " " + tip).trim(),
                    })
                  }
                >
                  + {tip.replace(" 강조", "").replace("강조", "")}
                </span>
              ))}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              hidden
              onChange={handleImageUpload}
            />
          </div>
          <div style={{ height: 1, background: "var(--line)" }} />
          <div>
            <div className="rail-label">02 · 스타일</div>
            <div
              style={{
                display: "flex",
                background: "rgba(255,255,255,.05)",
                borderRadius: 9,
                padding: 3,
                marginBottom: 11,
              }}
            >
              <div
                style={{
                  flex: 1,
                  textAlign: "center",
                  padding: 7,
                  borderRadius: 7,
                  fontSize: 11.5,
                  fontWeight: 700,
                  background: "rgba(242,169,59,.16)",
                  color: "var(--gold)",
                }}
              >
                ✨ AI 추천
              </div>
              <div
                style={{
                  flex: 1,
                  textAlign: "center",
                  padding: 7,
                  borderRadius: 7,
                  fontSize: 11.5,
                  fontWeight: 600,
                  color: "var(--ink-mute)",
                  cursor: "pointer",
                }}
                onClick={() => s.toast("직접 입력 모드 (목업)")}
              >
                ✍️ 직접 입력
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {STYLES.map(({ label, sw }) => (
                <button
                  key={label}
                  className={`style-row${s.styleLabel === label ? " on" : ""}`}
                  onClick={() => s.setDashboardState({ styleLabel: label })}
                >
                  <span className="sw" style={{ background: sw }} />
                  <span className="nm">{label}</span>
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="rail-label">템플릿 팩</div>
            <TemplateGrid
              activeStyleLabel={s.styleLabel}
              onPick={(t, styleLabel) => {
                const nextUse = FORMAT_TO_USE[t.formats[0] ?? ""];
                s.setDashboardState({
                  styleLabel,
                  ...(nextUse ? { useValue: nextUse } : {}),
                });
                s.toast(`템플릿 적용: ${t.title}`);
              }}
            />
          </div>
          <div>
            <div className="rail-label">03 · 용도</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {USES.map(({ v, label }) => (
                <button
                  key={v}
                  className={`use${s.useValue === v ? " on" : ""}`}
                  onClick={() => s.setDashboardState({ useValue: v })}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <button
            className="btn-gen"
            style={{ marginTop: "auto" }}
            disabled={loading}
            onClick={generate}
          >
            ✦ 광고 생성
          </button>
        </div>

        {/* CANVAS */}
        <div style={{ padding: 26, display: "flex", flexDirection: "column", gap: 16 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ fontSize: 13, color: "var(--ink-mute)" }}>
              결과{" "}
              <span style={{ color: "var(--ink)", fontWeight: 600 }}>
                · 원본 ⟷ AI 생성
              </span>
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-mute)" }}>
              {s.dashboardSummaryText}
            </div>
          </div>

          {loading ? (
            <div
              className="loading-panel"
              style={{
                flex: 1,
                minHeight: 420,
                border: "1px solid var(--line)",
                borderRadius: 16,
                background: "var(--card)",
              }}
            >
              <div className="ring" />
              <div className="st">{loadStep}</div>
              <div className="stp">광고를 만들고 있어요 (보통 1분 내외)</div>
            </div>
          ) : !result ? (
            <div
              className="result-empty"
              style={{
                flex: 1,
                minHeight: 420,
                border: "1px solid var(--line)",
                borderRadius: 16,
                background: "var(--card)",
              }}
            >
              <div className="big">🖼</div>
              <h3>아직 만든 광고가 없어요</h3>
              <p>
                왼쪽에서 재료를 넣고 <b>광고 생성</b>을 눌러보세요.
              </p>
            </div>
          ) : (
            <div>
              {hasTypographyPair && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    marginBottom: 12,
                    padding: "10px 13px",
                    border: "1px solid var(--line)",
                    borderRadius: 10,
                    background: "var(--card)",
                  }}
                >
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      color: "var(--ink-soft)",
                    }}
                  >
                    타이포 포함
                  </span>
                  <label
                    htmlFor="typographyToggle"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 7,
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    <input
                      id="typographyToggle"
                      type="checkbox"
                      checked={typographyOn}
                      onChange={(e) => setTypographyOn(e.target.checked)}
                    />
                    {typographyOn ? "포함" : "무타이포"}
                  </label>
                </div>
              )}
              <div
                className="compare-grid"
                style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}
              >
                <div
                  style={{
                    position: "relative",
                    borderRadius: 14,
                    overflow: "hidden",
                    minHeight: 360,
                    background: "#0d0d10",
                  }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={beforeSrc}
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                    }}
                    alt="원본"
                  />
                  <span
                    style={{
                      position: "absolute",
                      left: 12,
                      top: 12,
                      background: "rgba(0,0,0,.55)",
                      color: "var(--ink-soft)",
                      fontSize: 10,
                      fontWeight: 800,
                      letterSpacing: ".05em",
                      padding: "4px 9px",
                      borderRadius: 6,
                    }}
                  >
                    BEFORE
                  </span>
                </div>
                <div
                  style={{
                    position: "relative",
                    borderRadius: 14,
                    overflow: "hidden",
                    minHeight: 360,
                    background: "#0d0d10",
                  }}
                >
                  <AuthenticatedImage
                    src={toAbsoluteUrl(resultImageUrl(result))}
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                    }}
                    alt="AI 광고"
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
                      letterSpacing: ".05em",
                      padding: "4px 9px",
                      borderRadius: 6,
                    }}
                  >
                    AFTER
                  </span>
                  {!s.isPremium && (
                    <span
                      style={{
                        position: "absolute",
                        right: 12,
                        bottom: 12,
                        background: "rgba(0,0,0,.6)",
                        color: "var(--ink-soft)",
                        fontSize: 9,
                        fontWeight: 700,
                        padding: "4px 8px",
                        borderRadius: 6,
                      }}
                    >
                      🔖 워터마크
                    </span>
                  )}
                </div>
              </div>

              <div
                className="copy-block"
                style={{
                  background: "var(--card)",
                  border: "1px solid var(--line)",
                  borderRadius: 14,
                  padding: "16px 18px",
                  marginTop: 16,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 9,
                    marginBottom: 12,
                    flexWrap: "wrap",
                  }}
                >
                  <span style={{ fontSize: 12, fontWeight: 800, color: "var(--gold-deep)" }}>
                    ✦ 매체별 카피
                  </span>
                  <div className="plat-tabs" style={{ margin: "0 0 0 auto" }}>
                    {PLATFORMS.map(({ p, si, label, short }) => (
                      <button
                        key={p}
                        className={`ptab${activePlatform === p ? " on" : ""}`}
                        onClick={() => setActivePlatform(p)}
                      >
                        <span className={`si ${si}`}>{short}</span>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <h4>{platformCopy?.head}</h4>
                <p style={{ whiteSpace: "pre-line" }}>{platformCopy?.body}</p>
                <div className="tags">{platformCopy?.tags}</div>
              </div>

              <div className="out-actions">
                <button
                  className="oa save"
                  onClick={() => s.toast("생성 결과는 내 광고에 자동 저장돼요")}
                >
                  💾 저장
                </button>
                <button className="oa" onClick={downloadResult}>
                  ⬇️ 다운로드 {s.isPremium ? "" : "🔒"}
                </button>
                <button className="oa" onClick={shareCurrentResult}>
                  ↗️ 공유
                </button>
                <button className="oa" disabled={loading} onClick={regenerate}>
                  🔄 다시 생성
                </button>
              </div>
              {!s.isPremium && (
                <div className="wm-row">
                  <span className="wm-l">🔖 무료는 워터마크 미리보기만 제공돼요</span>
                  <button className="wm-up" onClick={() => router.push("/billing")}>
                    원본 다운로드 (프리미엄) →
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
