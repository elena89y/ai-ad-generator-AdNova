"use client";

/* v6 T4 — 템플릿 팩 그리드 (모노브 벤치마크 M5 대응).
   카드 선택 = 기존 스타일 상태(styleLabel)만 구동한다 — 생성 계약·Provider 확장 없음.
   썸네일은 인증 필요(/api/ads/template-thumb) → AuthenticatedImage 재사용. */

import { useEffect, useState } from "react";
import { STYLE_LABEL_MAP, toAbsoluteUrl } from "@/lib/api";
import { AdTemplate, fetchTemplates } from "@/lib/templates";
import { AuthenticatedImage } from "./AuthenticatedImage";

interface TemplateGridProps {
  activeStyleLabel: string;
  onPick: (template: AdTemplate, styleLabel: string) => void;
}

export function TemplateGrid({ activeStyleLabel, onPick }: TemplateGridProps) {
  const [templates, setTemplates] = useState<AdTemplate[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    fetchTemplates()
      .then((items) => {
        if (cancelled) return;
        setTemplates(items);
        setStatus("ready");
      })
      .catch(() => {
        if (!cancelled) setStatus("error"); // 템플릿은 부가 기능 — 실패해도 스튜디오는 동작
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "error") return null;
  if (status === "loading") {
    return (
      <div style={{ fontSize: 11.5, color: "var(--ink-mute)", padding: "6px 2px" }}>
        템플릿 불러오는 중…
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: 8, overflowX: "auto", paddingBottom: 4 }}>
      {templates.map((t) => {
        const styleLabel = STYLE_LABEL_MAP[t.style_preset] ?? t.style_preset;
        const on = styleLabel === activeStyleLabel;
        return (
          <button
            key={t.id}
            type="button"
            title={`${t.desc}\n무드: ${t.mood}`}
            onClick={() => onPick(t, styleLabel)}
            style={{
              flex: "0 0 auto",
              width: 92,
              padding: 4,
              borderRadius: 10,
              border: on ? "1.5px solid var(--gold)" : "1.5px solid transparent",
              background: on ? "rgba(242,169,59,.10)" : "transparent",
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            <div
              style={{
                width: "100%",
                aspectRatio: "4 / 5",
                borderRadius: 8,
                overflow: "hidden",
                background: t.palette[0] ?? "var(--ink-mute)",
              }}
            >
              <AuthenticatedImage
                src={toAbsoluteUrl(t.thumbnail ?? "")}
                alt={t.title}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            </div>
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                marginTop: 4,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {t.title}
            </div>
            <div style={{ display: "flex", gap: 3, marginTop: 3 }}>
              {t.palette.slice(0, 3).map((hex) => (
                <span
                  key={hex}
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 3,
                    background: hex,
                    display: "inline-block",
                  }}
                />
              ))}
            </div>
          </button>
        );
      })}
    </div>
  );
}
