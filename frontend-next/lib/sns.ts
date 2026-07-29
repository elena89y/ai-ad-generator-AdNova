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
 * → SNS 내보내기 API 호출
 * → 상세 화면의 플랫폼별 문구를 클립보드에 복사
 * → 모바일: 이미지 + 상세 화면 문구를 공유 시트로 전달
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
    * 1. 백엔드 SNS 내보내기 API 호출
    *
    * 기존 export API 연동은 유지한다.
    * 다만 백엔드가 반환한 post_text는 실제 공유 문구로 사용하지 않고,
    * 상세 화면에 표시된 플랫폼별 카피를 그대로 공유한다.
    */
    const exportResponse = await apiFetch("/api/export/sns", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        platform,
        image_url: toFullUrl(item.img),
        product_name:
          item.productName || item.hl || "광고 상품",
        headline:
          item.copyHead || item.hl || null,
        description:
          item.copyBody || null,
        style:
          item.style || null,
      }),
    });

    const exportData = await readJsonSafely(exportResponse);

    if (!exportResponse.ok) {
      throw new Error(
        readApiError(
          exportData,
          "SNS 공유 정보를 생성하지 못했습니다"
        )
      );
    }

    /*
    * 2. 상세 화면에 표시된 플랫폼별 문구를 그대로 사용
    *
    * 백엔드 응답의 exportData.post_text는 사용하지 않는다.
    */
    const postText = [
      item.copyHead,
      item.copyBody,
      item.copyTags,
    ]
      .filter(
        (value): value is string =>
          Boolean(value?.trim())
      )
      .map((value) => value.trim())
      .join("\n\n");

    if (!postText) {
      toast("공유할 게시글 문구가 없습니다");
      return;
    }

    /*
    * 3. 문구를 클립보드에 미리 복사
    */
    await copyTextSafely(postText);

    /*
     * 4. 공유할 이미지 다운로드
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
     * 5. 이미지 응답을 Blob으로 변환
     */
    const imageBlob = await imageResponse.blob();

    if (!imageBlob.type.startsWith("image/")) {
      throw new Error("공유할 파일이 이미지 형식이 아닙니다");
    }

    /*
     * 6. Blob을 공유 가능한 File 객체로 변환
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
     * 7. 모바일 기기 및 파일 공유 가능 여부 확인
     *
     * Windows도 navigator.share를 지원할 수 있으므로
     * 모바일 기기에서만 운영체제 공유 시트를 사용한다.
     */
    const isMobileDevice =
      typeof navigator !== "undefined" &&
      /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

    const canShareImage =
      isMobileDevice &&
      typeof navigator.share === "function" &&
      typeof navigator.canShare === "function" &&
      navigator.canShare({
        files: [imageFile],
      });

    /*
     * 8. 모바일: 운영체제 공유 시트 실행
     *
     * Instagram, Facebook, X, Threads 모두
     * 기기나 앱 환경에 따라 문구 자동 입력 여부가 달라질 수 있다.
     * 문구는 이미 클립보드에 복사되어 있다.
     */
    if (canShareImage) {
      await navigator.share({
        title: item.copyHead || item.hl || "AdNova 광고",
        text: postText,
        files: [imageFile],
      });

      toast(
        "이미지를 공유했어요. 문구가 자동 입력되지 않으면 붙여넣어 주세요."
      );

      return;
    }

    /*
     * 9. PC 또는 파일 공유 미지원 환경
     *
     * 이미지를 다운로드하고
     * 선택한 SNS 페이지를 새 창으로 연다.
     */
    downloadShareImage(imageFile);

    const shareUrls: Record<string, string> = {
      x: `https://x.com/intent/post?text=${encodeURIComponent(postText)}`,
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
  if (!historyId) {
    throw new Error("삭제할 광고 이력을 찾을 수 없습니다");
  }

  const res = await apiFetch(
    `/api/history/${historyId}/result`,
    {
      method: "DELETE",
    }
  );

  if (!res.ok) {
    const data = await readJsonSafely(res);
    throw new Error(
      readApiError(data, "광고 삭제에 실패했습니다")
    );
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
    const res = await apiFetch(
      `/api/history/${historyId}/result/download`
    );

    if (!res.ok) {
      const data = await readJsonSafely(res);
      throw new Error(
        readApiError(data, "광고 이미지를 다운로드하지 못했습니다")
      );
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
    toast(
      err instanceof Error
        ? err.message
        : "광고 이미지를 다운로드하지 못했습니다"
    );
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
    toast(
      err instanceof Error
        ? err.message
        : "광고 이미지를 다운로드하지 못했습니다"
    );
  }
}

function toFullUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }

  const path = toAbsoluteUrl(url) || url;

  if (/^https?:\/\//i.test(path)) {
    return path;
  }

  return `${window.location.origin}${
    path.startsWith("/") ? "" : "/"
  }${path}`;
}
