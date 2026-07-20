"use client";

import {
  type ImgHTMLAttributes,
  useEffect,
  useState,
} from "react";
import { getToken } from "@/lib/api";

type AuthenticatedImageProps = Omit<
  ImgHTMLAttributes<HTMLImageElement>,
  "src"
> & {
  src?: string | null;
};

function requiresToken(src: string): boolean {
  try {
    const url = new URL(src, window.location.origin);

    return url.pathname.startsWith("/api/ads/image/");
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

  useEffect(() => {
    if (!src) {
      setDisplaySrc("");
      return;
    }

    // src를 string 타입으로 고정
    const imageSrc = src;

    if (!requiresToken(imageSrc)) {
      setDisplaySrc(imageSrc);
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
        }
      } catch (error) {
        console.error("인증 이미지 로딩 실패:", error);

        if (!cancelled) {
          setDisplaySrc("");
        }
      }
    }

    setDisplaySrc("");
    void loadImage();

    return () => {
      cancelled = true;

      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [src]);

  if (!displaySrc) {
    return null;
  }

  // eslint-disable-next-line @next/next/no-img-element
  return <img {...props} src={displaySrc} alt={alt ?? ""} />;
}