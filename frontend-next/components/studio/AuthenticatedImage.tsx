"use client";

import {
  type CSSProperties,
  type ImgHTMLAttributes,
  useEffect,
  useState,
} from "react";
import { getToken } from "@/lib/api";

type AuthenticatedImageProps = Pick<
  ImgHTMLAttributes<HTMLImageElement>,
  "alt" | "className" | "style"
> & {
  src?: string | null;
};

function requiresToken(src: string): boolean {
  try {
    const url = new URL(src, window.location.origin);

    return (
      url.pathname.startsWith("/api/ads/image/") ||
      url.pathname.startsWith("/api/ads/template-thumb/") // v6 T4 템플릿 썸네일도 인증 필요
    );
  } catch {
    return false;
  }
}

export function AuthenticatedImage({
  src,
  alt,
  className,
  style,
  ...props
}: AuthenticatedImageProps) {
  const [displaySrc, setDisplaySrc] = useState("");
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (!src) {
      setDisplaySrc("");
      setLoadState("error");
      return;
    }

    // src를 string 타입으로 고정
    const imageSrc = src;

    if (!requiresToken(imageSrc)) {
      setDisplaySrc(imageSrc);
      setLoadState("ready");
      return;
    }

    let objectUrl: string | null = null;
    let cancelled = false;

    async function loadImage() {
      try {
        const token = getToken();

        const response = await fetch(imageSrc, {
          headers: token
            ? {
                Authorization: `Bearer ${token}`,
              }
            : undefined,
        });

        if (!response.ok) {
          throw new Error(
            `이미지를 불러오지 못했습니다: ${response.status}`,
          );
        }

        const blob = await response.blob();
        objectUrl = URL.createObjectURL(blob);

        if (!cancelled) {
          setDisplaySrc(objectUrl);
          setLoadState("ready");
        }
      } catch (error) {
        console.error("인증 이미지 로딩 실패:", error);

        if (!cancelled) {
          setDisplaySrc("");
          setLoadState("error");
        }
      }
    }

    setDisplaySrc("");
    setLoadState("loading");
    void loadImage();

    return () => {
      cancelled = true;

      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [src, retryKey]);

  if (!displaySrc || loadState !== "ready") {
    const stateStyle: CSSProperties = {
      ...style,
      display: "grid",
      placeItems: "center",
      gap: 8,
      padding: 12,
      background: "rgba(13,13,16,.82)",
      color: "var(--ink-mute)",
      fontSize: 12,
      textAlign: "center",
    };

    return (
      <div className={className} style={stateStyle} role="img" aria-label={alt || "광고 이미지"}>
        {loadState === "error" ? (
          <>
            <span>이미지를 불러오지 못했습니다</span>
            {src && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setRetryKey((value) => value + 1);
                }}
                style={{
                  border: "1px solid rgba(255,255,255,.22)",
                  borderRadius: 6,
                  background: "transparent",
                  color: "var(--ink-soft)",
                  padding: "4px 8px",
                  fontSize: 11,
                  cursor: "pointer",
                }}
              >
                다시 시도
              </button>
            )}
          </>
        ) : (
          <span>이미지를 불러오는 중입니다</span>
        )}
      </div>
    );
  }

  // eslint-disable-next-line @next/next/no-img-element
  return (
    <img
      {...props}
      src={displaySrc}
      alt={alt ?? ""}
      onError={() => {
        setDisplaySrc("");
        setLoadState("error");
      }}
    />
  );
}
