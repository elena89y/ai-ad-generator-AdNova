/* v6 T4 — 템플릿 프리셋 API 클라이언트 (GET /ads/templates)
   백엔드 원장: backend/app/templates/templates.yaml — 신규 템플릿은 YAML 추가만.
   선택된 템플릿의 style_preset/knob 을 기존 /ads/generate 폼에 그대로 싣는다(신규 생성 계약 없음). */

import { apiFetch, readApiError, readJsonSafely } from "@/lib/api";

export interface AdTemplate {
  id: string;
  title: string;
  desc: string;
  style: string; // style_specs 키 (백엔드 내부용)
  style_preset: string; // /ads/generate 전송값 (StylePreset enum)
  target: "food" | "drink" | "object" | "any";
  formats: string[];
  knob: number | null;
  thumbnail: string | null; // {API_PREFIX}/ads/template-thumb/{id}
  palette: string[];
  mood: string;
}

export async function fetchTemplates(target?: string): Promise<AdTemplate[]> {
  const query = target ? `?target=${encodeURIComponent(target)}` : "";
  const res = await apiFetch(`/ads/templates${query}`);
  const data = await readJsonSafely(res);
  if (!res.ok) {
    throw new Error(readApiError(data, "템플릿을 불러오지 못했습니다"));
  }
  return (data as AdTemplate[]) ?? [];
}
