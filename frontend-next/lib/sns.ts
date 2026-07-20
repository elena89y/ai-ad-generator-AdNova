import {
  AdItem,
  apiFetch,
  copyTextSafely,
  getToken,
  readApiError,
  readJsonSafely,
} from "./api";

export const SNS_LIST = [
  { k: "ig", n: "Instagram", p: "instagram" },
  { k: "fb", n: "Facebook", p: "facebook" },
  { k: "x", n: "X (Twitter)", p: "x" },
  { k: "th", n: "Threads", p: "threads" },
];

export const PLATFORM_NAMES: Record<string, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  x: "X",
  threads: "Threads",
};

/* POST /api/export/sns → 문구 복사 + 공유 페이지 열기 (프로토타입 exportSnsPost 포팅) */
export async function exportSnsPost(
  platform: string,
  item: Partial<AdItem>,
  toast: (msg: string) => void
): Promise<void> {
  if (!getToken()) {
    toast("로그인 후 공유해 주세요");
    return;
  }
  if (!item || !item.img) {
    toast("공유할 광고 이미지가 없습니다");
    return;
  }
  try {
    const res = await apiFetch("/api/export/sns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        platform,
        image_url: item.img,
        product_name: item.productName || item.hl || "광고 상품",
        headline: item.copyHead || item.hl || null,
        description: item.copyBody || null,
        style: item.style || null,
      }),
    });
    const data = (await readJsonSafely(res)) as { post_text?: string } | null;
    if (!res.ok || !data?.post_text)
      throw new Error(readApiError(data, "SNS 공유 문구를 만들지 못했습니다"));
    await copyTextSafely(data.post_text);
    const shareUrls: Record<string, string> = {
      x: `https://twitter.com/intent/tweet?text=${encodeURIComponent(data.post_text)}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(item.img)}`,
      instagram: "https://www.instagram.com/",
      threads: "https://www.threads.net/",
    };
    const shareUrl = shareUrls[platform];
    if (!shareUrl) throw new Error("지원하지 않는 SNS입니다");
    window.open(shareUrl, "_blank", "noopener,noreferrer");
    toast(`${PLATFORM_NAMES[platform] || platform}용 문구를 복사하고 공유 페이지를 열었어요`);
  } catch (err) {
    toast(err instanceof Error ? err.message : "SNS 공유 문구를 만들지 못했습니다");
  }
}

export async function deleteStoredAd(historyId?: number): Promise<void> {
  if (!historyId) throw new Error("삭제할 광고 이력을 찾을 수 없습니다");
  const res = await apiFetch(`/api/history/${historyId}/result`, { method: "DELETE" });
  if (!res.ok) {
    const data = await readJsonSafely(res);
    throw new Error(readApiError(data, "광고 삭제에 실패했습니다"));
  }
}

export async function downloadHistoryResult(
  historyId: number | undefined,
  toast: (msg: string) => void
): Promise<void> {
  if (!historyId) {
    toast("다운로드할 광고 이력을 찾을 수 없습니다");
    return;
  }
  try {
    const res = await apiFetch(`/api/history/${historyId}/result/download`);
    if (!res.ok) {
      const data = await readJsonSafely(res);
      throw new Error(readApiError(data, "광고 이미지를 다운로드하지 못했습니다"));
    }
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "adnova-ad.png";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
    toast("고해상도 원본을 다운로드했어요");
  } catch (err) {
    toast(err instanceof Error ? err.message : "광고 이미지를 다운로드하지 못했습니다");
  }
}
