"use client";

/* v6 TEMPLATE-PIPE-V2 — 템플릿 전용 광고 만들기 페이지.
   /templates/[id] : 갤러리에서 진입 → 프리뷰 + 사진 업로드 + 상품명 → template_id 생성.
   studio(스타일 프리셋) 경로를 거치지 않고, 백엔드가 서버측 연출 레시피로 생성한다.
   서버 template_id = tpl_{NN}_{id} (catalog_v1.json 키). identity_grade 보존은 서버가 처리. */

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import {
  apiFetch,
  getToken,
  readApiError,
  readJsonSafely,
  toAbsoluteUrl,
} from "@/lib/api";
import { CATALOG } from "@/lib/catalog";
import { useStudio } from "@/components/studio/StudioProvider";
import { AppBar, WorkspaceNav } from "@/components/studio/chrome";
import { AuthenticatedImage } from "@/components/studio/AuthenticatedImage";

const GEN_STEPS = ["사진을 분석하는 중…", "템플릿 연출을 입히는 중…", "광고 문구를 쓰는 중…", "마무리하는 중…"];

function serverTemplateId(no: number, id: string): string {
  return `tpl_${String(no).padStart(2, "0")}_${id}`;
}

export default function TemplateApplyPage() {
  const s = useStudio();
  const router = useRouter();
  const params = useParams();
  const idParam = String(params.id ?? "");
  const tpl = useMemo(() => CATALOG.find((e) => e.id === idParam), [idParam]);

  const fileRef = useRef<HTMLInputElement>(null);
  const [imageId, setImageId] = useState<number | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [productName, setProductName] = useState("");
  const [extraRequest, setExtraRequest] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadStep, setLoadStep] = useState(GEN_STEPS[0]);
  const [resultUrl, setResultUrl] = useState<string>("");
  const stepTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (s.ready && !s.token) router.replace("/login");
  }, [s.ready, s.token, router]);

  async function uploadProductImage(file: File | undefined) {
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) {
      s.toast("이미지는 최대 15MB까지 업로드할 수 있습니다.");
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    try {
      s.toast("이미지를 업로드하는 중입니다");
      const res = await apiFetch("/api/images/upload", { method: "POST", body: fd });
      const data = (await readJsonSafely(res)) as { image_id?: number; image_url?: string } | null;
      if (!res.ok || !data?.image_id || !data.image_url)
        throw new Error(readApiError(data, "이미지 업로드에 실패했습니다"));
      setImageId(data.image_id);
      setPreview(toAbsoluteUrl(data.image_url));
      setResultUrl("");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "이미지 업로드에 실패했습니다");
    }
  }

  function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    void uploadProductImage(file);
  }

  function handleImageDrop(event: DragEvent<HTMLButtonElement>) {
    event.preventDefault();
    void uploadProductImage(event.dataTransfer.files?.[0]);
  }

  async function generate() {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    if (!tpl) return;
    if (imageId == null) {
      s.toast("제품 사진을 먼저 올려주세요");
      return;
    }
    setLoading(true);
    let i = 0;
    setLoadStep(GEN_STEPS[0]);
    stepTimer.current = setInterval(() => {
      i = Math.min(i + 1, GEN_STEPS.length - 1);
      setLoadStep(GEN_STEPS[i]);
    }, 4000);
    try {
      const fd = new FormData();
      fd.append("image_id", String(imageId));
      // 상품명 미입력 시 빈 값 그대로 전송 — 템플릿 표시명을 폴백하면 각인류 템플릿이
      // 그 이름("크림 각인 타이포")을 문자 그대로 새기는 사고가 남 (2026-07-24 실측)
      fd.append("product_name", productName.trim());
      if (extraRequest.trim()) fd.append("extra_request", extraRequest.trim());
      fd.append("template_id", serverTemplateId(tpl.no, tpl.id));
      fd.append("purpose", "sns");
      const res = await apiFetch("/api/ads/generate", { method: "POST", body: fd });
      const data = (await readJsonSafely(res)) as { image_url?: string } | null;
      if (!res.ok || !data?.image_url) throw new Error(readApiError(data, "광고 생성에 실패했습니다"));
      setResultUrl(toAbsoluteUrl(data.image_url) ?? "");
      s.refreshBilling(false);
      s.refreshHistory(false);
      s.refreshDashboardSummary();
      s.toast("광고가 완성됐어요");
    } catch (err) {
      s.toast(err instanceof Error ? err.message : "광고 생성에 실패했습니다");
    } finally {
      if (stepTimer.current) clearInterval(stepTimer.current);
      setLoading(false);
    }
  }

  if (!tpl) {
    return (
      <section>
        <AppBar />
        <div className="workspace-shell">
          <WorkspaceNav />
          <main style={{ flex: 1, padding: 40 }}>
            <p style={{ color: "var(--ink-mute)" }}>템플릿을 찾을 수 없어요.</p>
            <button className="btn-gen" style={{ marginTop: 16, maxWidth: 200 }} onClick={() => router.push("/templates")}>
              템플릿 목록으로
            </button>
          </main>
        </div>
      </section>
    );
  }

  return (
    <section>
      <AppBar />
      <div className="workspace-shell">
        <WorkspaceNav />
        <main style={{ flex: 1, minWidth: 0, padding: "24px 26px 60px" }}>
          <button
            onClick={() => router.push("/templates")}
            style={{ border: 0, background: "transparent", color: "var(--ink-mute)", fontSize: 13, cursor: "pointer", marginBottom: 12 }}
          >
            ← 템플릿
          </button>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 24, alignItems: "start" }}>
            {/* 템플릿 프리뷰 */}
            <div>
              <div style={{ borderRadius: 16, overflow: "hidden", border: "1px solid var(--line)" }}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={tpl.img} alt={tpl.name} style={{ width: "100%", display: "block" }} />
              </div>
              <h1 style={{ fontSize: 19, fontWeight: 800, marginTop: 14 }}>{tpl.name}</h1>
              <p style={{ fontSize: 13, color: "var(--ink-soft)", marginTop: 4, lineHeight: 1.6 }}>{tpl.desc}</p>
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 8 }}>
                {tpl.tags.map((tg) => (
                  <span key={tg} style={{ fontSize: 11, padding: "3px 9px", borderRadius: 999, background: "rgba(255,255,255,.06)", color: "var(--ink-soft)" }}>{tg}</span>
                ))}
              </div>
            </div>

            {/* 입력 & 생성 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <div className="rail-label">제품 사진</div>
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={handleImageDrop}
                  style={{
                    width: "100%", aspectRatio: "1/1", maxHeight: 300, borderRadius: 12,
                    border: "1px dashed var(--line)", background: "rgba(255,255,255,.03)",
                    cursor: "pointer", overflow: "hidden", display: "flex", alignItems: "center",
                    justifyContent: "center", color: "var(--ink-mute)", fontSize: 13,
                  }}
                >
                  {preview ? (
                    <AuthenticatedImage src={preview} alt="업로드" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                  ) : (
                    "클릭하거나 사진을 끌어다 놓으세요"
                  )}
                </button>
                <input ref={fileRef} type="file" accept="image/*,.heic,.heif" hidden onChange={handleUpload} />
              </div>

              <div>
                <div className="rail-label">상품명 (선택)</div>
                <input
                  className="rail-input"
                  value={productName}
                  onChange={(e) => setProductName(e.target.value)}
                  placeholder={`예: ${tpl.name_examples?.join(", ") ?? tpl.name}`}
                />
              </div>

              <div>
                <div className="rail-label">추가 요청 (선택)</div>
                <textarea
                  className="rail-input"
                  value={extraRequest}
                  onChange={(e) => setExtraRequest(e.target.value)}
                  rows={2}
                  style={{ resize: "vertical" }}
                  placeholder={
                    tpl.request_examples?.length
                      ? `예: ${tpl.request_examples.join(" · ")}`
                      : "예: 배경을 더 밝게 · 그림자 길게"
                  }
                />
              </div>

              <button className="btn-gen" disabled={loading || imageId == null} onClick={generate}>
                {loading ? loadStep : "✦ 이 템플릿으로 광고 만들기"}
              </button>

              {resultUrl && (
                <div style={{ marginTop: 8 }}>
                  <div className="rail-label">완성된 광고</div>
                  <div style={{ borderRadius: 12, overflow: "hidden", border: "1px solid var(--line)" }}>
                    <AuthenticatedImage src={resultUrl} alt="완성 광고" style={{ width: "100%", display: "block" }} />
                  </div>
                  <button
                    className="btn-gen"
                    style={{ marginTop: 10 }}
                    onClick={() => router.push("/my-ads")}
                  >
                    내 광고에서 보기 →
                  </button>
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </section>
  );
}
