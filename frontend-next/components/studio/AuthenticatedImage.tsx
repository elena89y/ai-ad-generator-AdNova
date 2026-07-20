"use client";

import { ImgHTMLAttributes, useEffect, useState } from "react";
import { getToken } from "@/lib/api";

type AuthenticatedImageProps = Omit<ImgHTMLAttributes<HTMLImageElement>, "src"> & {
  src?: string | null;
};

function requiresToken(src: string) {
  try {
    return new URL(src, window.location.origin).pathname.startsWith("/api/ads/image/");
  } catch {
    return false;
  }
}

export function AuthenticatedImage({ src, alt, ...props }: AuthenticatedImageProps) {
  const [displaySrc, setDisplaySrc] = useState("");

  useEffect(() => {
    if (!src) {
      setDisplaySrc("");
      return;
    }
    if (!requiresToken(src)) {
      setDisplaySrc(src);
      return;
    }

    let objectUrl = "";
    let cancelled = false;

    async function loadImage() {
      try {
        const token = getToken();
        const response = await fetch(src, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!response.ok) throw new Error("이미지를 불러오지 못했습니다");

        objectUrl = URL.createObjectURL(await response.blob());
        if (!cancelled) setDisplaySrc(objectUrl);
      } catch {
        if (!cancelled) setDisplaySrc("");
      }
    }

    setDisplaySrc("");
    void loadImage();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  if (!displaySrc) return null;
  // eslint-disable-next-line @next/next/no-img-element
  return <img {...props} src={displaySrc} alt={alt ?? ""} />;
}
