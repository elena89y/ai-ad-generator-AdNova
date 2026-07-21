import {
  AdItem,
  apiFetch,
  copyTextSafely,
  getToken,
  readApiError,
  readJsonSafely,
  toAbsoluteUrl,
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

/* POST /api/export/sns
 * → SNS 문구 생성
 * → 문구 클립보드 복사
 * → 모바일: 이미지 + 문구를 공유 시트로 전달
 * → PC: 이미지 다운로드 + SNS 페이지 열기
 */
export async function exportSnsPost(
  platform: string,
  item: Partial<AdItem>,
  toast: (msg: string) => void
): Promise<void> {
  const token = getToken();

  if (!token) {
    toast("로그인 후 공유해 주세요");
    return;
  }

  if (!item?.img) {
    toast("공유할 광고 이미지가 없습니다");
    return;
  }

  try {
    /*
     * 1. 백엔드에서 SNS용 문구 생성
     */
    const res = await apiFetch("/api/export/sns", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        platform,
        image_url: toFullUrl(item.img),
        product_name: item.productName || item.hl || "광고 상품",
        headline: item.copyHead || item.hl || null,
        description: item.copyBody || null,
        style: item.style || null,
      }),
    });

    const data = (await readJsonSafely(res)) as {
      post_text?: string;
    } | null;

    if (!res.ok || !data?.post_text) {
      throw new Error(
        readApiError(data, "SNS 공유 문구를 만들지 못했습니다")
      );
    }

    const postText = data.post_text;

    /*
     * 2. 문구를 클립보드에 미리 복사
     *
     * Instagram 등 일부 앱은 공유된 text를
     * 게시물 본문에 넣지 않을 수 있기 때문에
     * 사용자가 직접 붙여넣을 수 있도록 복사한다.
     */
    await copyTextSafely(postText);

    /*
     * 3. 공유할 이미지 다운로드
     *
     * 저장된 광고라면 history 다운로드 API를 우선 사용한다.
     * 해당 API는 인증된 원본 이미지를 반환한다.
     */
    let imageResponse: Response;

    if (item.historyId) {
      imageResponse = await apiFetch(
        `/api/history/${item.historyId}/result/download`
      );
    } else {
      /*
       * historyId가 없는 임시 광고라면
       * 현재 이미지 URL을 직접 요청한다.
       */
      imageResponse = await fetch(item.img, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
    }

    if (!imageResponse.ok) {
      let errorMessage = "광고 이미지를 불러오지 못했습니다";

      try {
        const errorData = await readJsonSafely(imageResponse);
        errorMessage = readApiError(errorData, errorMessage);
      } catch {
        // 이미지 응답 등 JSON이 아닌 경우 기본 메시지를 사용한다.
      }

      throw new Error(errorMessage);
    }

    /*
     * 4. 이미지 응답을 Blob으로 변환
     */
    const imageBlob = await imageResponse.blob();

    if (!imageBlob.type.startsWith("image/")) {
      throw new Error("공유할 파일이 이미지 형식이 아닙니다");
    }

    /*
     * 5. Blob을 공유 가능한 File 객체로 변환
     */
    const extension = getImageExtension(imageBlob.type);

    const imageFile = new File(
      [imageBlob],
      `adnova-ad-${Date.now()}.${extension}`,
      {
        type: imageBlob.type,
      }
    );

    /*
     * 6. 모바일 파일 공유 가능 여부 확인
     */
    const canShareImage =
      typeof navigator !== "undefined" &&
      typeof navigator.share === "function" &&
      typeof navigator.canShare === "function" &&
      navigator.canShare({
        files: [imageFile],
      });

    /*
     * 7. 모바일: 운영체제 공유 시트 실행
     *
     * 사용자가 Instagram, Facebook, X, Threads 등을
     * 직접 선택하고 내용을 수정한 뒤 게시한다.
     */
    if (canShareImage) {
      await navigator.share({
        title: item.copyHead || item.hl || "AdNova 광고",
        text: postText,
        files: [imageFile],
      });

      toast(
        "공유창을 열었어요. 문구가 자동 입력되지 않으면 붙여넣기 해주세요"
      );

      return;
    }

    /*
     * 8. PC 또는 파일 공유 미지원 환경
     *
     * 이미지를 다운로드하고
     * 선택한 SNS 페이지를 새 창으로 연다.
     */
    downloadShareImage(imageFile);

    const shareUrls: Record<string, string> = {
      x: `https://twitter.com/intent/tweet?text=${encodeURIComponent(
        postText
      )}`,
      facebook: "https://www.facebook.com/",
      instagram: "https://www.instagram.com/",
      threads: "https://www.threads.net/",
    };

    const shareUrl = shareUrls[platform];

    if (!shareUrl) {
      throw new Error("지원하지 않는 SNS입니다");
    }

    window.open(
      shareUrl,
      "_blank",
      "noopener,noreferrer"
    );

    toast(
      `${
        PLATFORM_NAMES[platform] || platform
      }용 문구를 복사하고 이미지를 다운로드했어요`
    );
  } catch (err) {
    /*
     * 사용자가 모바일 공유창에서 취소한 경우
     * 오류 토스트를 띄우지 않는다.
     */
    if (
      err instanceof DOMException &&
      err.name === "AbortError"
    ) {
      return;
    }

    console.error("SNS 공유 실패:", err);

    toast(
      err instanceof Error
        ? err.message
        : "SNS 공유 중 오류가 발생했습니다"
    );
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

function getImageExtension(mimeType: string): string {
  switch (mimeType) {
    case "image/jpeg":
      return "jpg";

    case "image/webp":
      return "webp";

    case "image/gif":
      return "gif";

    case "image/png":
    default:
      return "png";
  }
}

function downloadShareImage(file: File): void {
  const objectUrl = URL.createObjectURL(file);

  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = file.name;

  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(objectUrl);
}

export async function downloadImageUrl(
  imageUrl: string,
  toast: (msg: string) => void
): Promise<void> {
  try {
    const res = await apiFetch(imageUrl);
    if (!res.ok) {
      throw new Error("광고 이미지를 다운로드하지 못했습니다");
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
    toast("이미지를 다운로드했어요");
  } catch (err) {
    toast(err instanceof Error ? err.message : "광고 이미지를 다운로드하지 못했습니다");
  }
}

// 헬퍼 추가
function toFullUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  const path = toAbsoluteUrl(url) || url;   // API base 경로 보정
  if (/^https?:\/\//i.test(path)) return path;
  return `${window.location.origin}${path.startsWith("/") ? "" : "/"}${path}`;
}
