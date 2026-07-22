import { CATALOG } from "./catalog";

/* 프로토타입(frontend/html/index.html)의 backend api 유틸 포팅 */

/* 로그인 API와 같은 기준을 사용한다.
   기본값은 same-origin /api, 별도 백엔드는 http://host:8000/api 형태로 설정한다. */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "/api").replace(
  /\/$/,
  ""
);

const ACCESS_TOKEN_KEY = "access_token";
const USER_KEY = "user";
const SESSION_ACCESS_TOKEN_KEY = ACCESS_TOKEN_KEY;
const SESSION_USER_KEY = USER_KEY;
export const AUTH_EXPIRED_EVENT = "adnova:auth-expired";
let refreshPromise: Promise<string | null> | null = null;

function buildApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const baseIncludesApi = API_BASE_URL === "/api" || API_BASE_URL.endsWith("/api");
  const pathWithoutDuplicateApi =
    baseIncludesApi && normalizedPath.startsWith("/api/")
      ? normalizedPath.slice(4)
      : normalizedPath;

  return `${API_BASE_URL}${pathWithoutDuplicateApi}`;
}

export const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const USERNAME_PATTERN = /^[A-Za-z0-9]{7,12}$/;
export const PASSWORD_PATTERN =
  /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&^#()_\-+=])[A-Za-z\d@$!%*?&^#()_\-+=]{8,20}$/;
export const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

export const STYLE_PRESET_MAP: Record<string, string> = {
  모노톤: "monotone",
  "웜 빈티지": "warm_vintage",
  "팝 비비드": "pop",
  에디토리얼: "editorial",
  리얼리즘: "retro_paper",
  파스텔: "pastel_float",
};
export const STYLE_LABEL_MAP: Record<string, string> = {
  monotone: "모노톤",
  warm_vintage: "웜 빈티지",
  pop: "팝 비비드",
  editorial: "에디토리얼",
  retro_paper: "리얼리즘",
  pastel_float: "파스텔",
};

const FIELD_LABELS: Record<string, string> = {
  email: "이메일",
  username: "아이디",
  password: "비밀번호",
  business_name: "상호명",
};

export interface AdnovaUser {
  id: number | null;
  email: string;
  username?: string;
  name?: string | null;
  business_name?: string | null;
  business_type?: string | null;
  auth_provider?: string;
  is_active?: boolean;
}

export interface PlatformCopy {
  head: string;
  body: string;
  tags: string;
}

export interface GenerateResult {
  history_id?: number;
  asset_id?: string;
  seed?: number;
  style?: string;
  image_url?: string;
  // [html-parity] 타이포 포함/무타이포 페어. 모놀리식 frontend/html/index.html에는
  // 있었으나 Next 이관 시 누락 — 백엔드가 반환하는 두 URL이 타입에 없어 버려지고 있었음.
  image_with_typography_url?: string;
  image_without_typography_url?: string;
  copy_text?: string;
  poster?: boolean;
  platform_copies?: Record<string, unknown>;
  // [html-parity] purpose별 포맷 산출물 URL 목록 + 그 purpose. Next 이관 시 누락되어
  // 용도별 결과(카드뉴스·배너·상세페이지)가 화면에 아예 표시되지 않던 원인.
  format_outputs?: string[];
  purpose?: string;
}

export interface AdItem {
  historyId?: number;
  advertisementId?: number;
  emoji: string;
  hl: string;
  copyHead: string;
  copyBody: string;
  copyTags?: string;
  platformCopies: Record<string, unknown>;
  productName: string;
  style: string;
  rawStyle?: string;
  date: string;
  createdAt?: string;
  inputImg: string;
  img: string;
  /* [v6-1] 용도별 산출물(상세페이지/카드뉴스/배너 여러 장)과 그 purpose.
     img 는 대표 히어로 1장(SNS 공유용) 유지 — 실제 포맷 결과는 여기로 렌더. */
  formatOutputs?: string[];
  purpose?: string;
  // [html-parity] 상세 화면 타이포 토글용 페어 — html buildCurrentOutputItem 이식 (Next 이관 시 누락)
  imageWithoutTypography?: string;
  imageWithTypography?: string;
  assetId?: string;
  seed?: number;
  adType?: string;
  productDescription?: string;
  g: string;
  prod: string;
}

export interface BillingSummary {
  is_premium: boolean;
  free_credits_remaining: number;
  free_credit_limit: number;
  next_free_credit_at?: string | null;
  premium_credits_remaining?: number | null;
  premium_credit_limit?: number;
  next_premium_credit_at?: string | null;
  subscription?: {
    plan?: string;
    status?: string;
    cancel_at_period_end?: boolean;
    current_period_end?: string;
  } | null;
  payment_method?: { card_brand?: string; card_last4?: string } | null;
}

export interface PurchaseHistory {
  purchased_at?: string;
  description?: string;
  status?: string;
  amount?: number;
  currency?: string;
}

/* ---------- auth storage ---------- */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY) || sessionStorage.getItem(SESSION_ACCESS_TOKEN_KEY);
}
export function getStoredUser(): AdnovaUser | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(
      localStorage.getItem(USER_KEY) || sessionStorage.getItem(SESSION_USER_KEY) || "null"
    );
  } catch {
    return null;
  }
}
export function isPersistentAuth(): boolean {
  return typeof window !== "undefined" && Boolean(localStorage.getItem(ACCESS_TOKEN_KEY));
}
export function storeAuth(token: string, user?: AdnovaUser | null, rememberMe = false) {
  const storage = rememberMe ? localStorage : sessionStorage;
  const otherStorage = rememberMe ? sessionStorage : localStorage;
  otherStorage.removeItem(ACCESS_TOKEN_KEY);
  otherStorage.removeItem(USER_KEY);
  storage.setItem(ACCESS_TOKEN_KEY, token);
  if (user) storage.setItem(USER_KEY, JSON.stringify(user));
}
export function clearStoredAuth() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  sessionStorage.removeItem(SESSION_ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(SESSION_USER_KEY);
}

export function getAuthProvider(): string {
  const stored = getStoredUser()?.auth_provider;
  if (stored) return stored;
  try {
    const payload = getToken()!.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload + "=".repeat((4 - (payload.length % 4)) % 4);
    const decoded = JSON.parse(atob(padded));
    return decoded.auth_provider || decoded.provider || "local";
  } catch {
    return "local";
  }
}
export function isSocialAuthUser(): boolean {
  return ["google", "kakao", "naver"].includes(getAuthProvider());
}

/* ---------- fetch ---------- */
async function requestApi(path: string, options: RequestInit = {}, token = getToken()) {
  return fetch(buildApiUrl(path), {
    ...options,
    credentials: "include",
    headers: {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
}

export async function refreshAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  if (!refreshPromise) {
    refreshPromise = fetch(buildApiUrl("/auth/refresh"), {
      method: "POST",
      credentials: "include",
    })
      .then(async (response) => {
        const data = (await readJsonSafely(response)) as { access_token?: string } | null;
        if (!response.ok || !data?.access_token) return null;
        storeAuth(data.access_token, getStoredUser(), isPersistentAuth());
        return data.access_token;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function logoutSession(): Promise<void> {
  try {
    await fetch(buildApiUrl("/auth/logout"), { method: "POST", credentials: "include" });
  } finally {
    clearStoredAuth();
  }
}

export async function apiFetch(path: string, options: RequestInit = {}) {
  let response = await requestApi(path, options);

  if (
    response.status === 401 &&
    path !== "/auth/refresh" &&
    path !== "/auth/logout" &&
    path !== "/api/auth/refresh" &&
    path !== "/api/auth/logout"
  ) {
    const refreshedToken = await refreshAccessToken();
    if (refreshedToken) response = await requestApi(path, options, refreshedToken);
  }

  if (response.status === 401 && typeof window !== "undefined") {
    clearStoredAuth();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }

  return response;
}

interface ValidationItem {
  loc?: unknown[];
  msg?: string;
  message?: string;
}

function fieldNameFromError(item: ValidationItem) {
  const loc = Array.isArray(item.loc) ? item.loc : [];
  const field = String(loc[loc.length - 1] ?? "");
  return FIELD_LABELS[field] || "입력값";
}
function formatValidationError(item: ValidationItem) {
  const field = fieldNameFromError(item);
  const msg = item.msg || item.message || "형식이 올바르지 않습니다";
  if (field === "이메일") return "이메일 형식이 올바르지 않습니다.";
  if (field === "아이디")
    return "아이디는 영문과 숫자만 사용해서 7~12자로 입력해 주세요.";
  if (field === "비밀번호")
    return "비밀번호는 8~20자이며 대문자, 소문자, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다.";
  if (msg.includes("String should have at most")) return `${field}이 너무 깁니다.`;
  if (msg.includes("String should have at least")) return `${field}이 너무 짧습니다.`;
  return `${field}: ${msg}`;
}
export function readApiError(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(formatValidationError).join("\n");
  return fallback;
}
export async function readJsonSafely(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

/* ---------- helpers ---------- */
export function toAbsoluteUrl(url?: string | null): string {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("data:"))
    return url;
  return buildApiUrl(url);
}

export interface NotificationSettings {
  ad_generation_complete_email: boolean;
  credit_depletion_alert: boolean;
  marketing_updates: boolean;
}

export interface ProfileImageResponse {
  image_url: string | null;
}
export function splitCopyText(text?: string | null): { head: string; body: string } {
  const lines = (text || "").split("\n").map((v) => v.trim()).filter(Boolean);
  return {
    head: lines[0] || "새 광고가 완성됐어요",
    body: lines.slice(1).join("\n") || lines[0] || "생성된 광고 문구를 확인해 주세요.",
  };
}
export function formatDateLabel(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getMonth() + 1}월 ${date.getDate()}일`;
}
export function toStyleLabel(style?: string | null): string {
  return STYLE_LABEL_MAP[style || ""] || style || "팝 비비드";
}
export function normalizePlatformCopy(
  value: unknown,
  fallback: PlatformCopy
): PlatformCopy {
  if (!value || typeof value !== "object") return fallback;
  const v = value as Record<string, unknown>;
  const rawTags = v.hashtags || v.tags || fallback.tags || "";
  return {
    head: String(v.headline || v.head || fallback.head || "").trim() || fallback.head,
    body: String(v.body || fallback.body || "").trim() || fallback.body,
    tags: Array.isArray(rawTags) ? rawTags.join(" ") : String(rawTags || fallback.tags),
  };
}
export function getItemPlatformCopy(
  item: Partial<AdItem> | null,
  platform: string
): PlatformCopy {
  const fallback: PlatformCopy = {
    head: item?.copyHead || item?.hl || item?.productName || "광고 문구",
    body: item?.copyBody || "",
    tags: item?.copyTags || `#AI광고 #AdNova #${item?.style || "광고"}`,
  };
  return normalizePlatformCopy(item?.platformCopies?.[platform], fallback);
}
export function formatAdType(type?: string): string {
  if (type === "poster") return "포스터";
  if (type === "image") return "이미지";
  return type || "이미지";
}

interface HistoryEntry {
  id: number;
  status?: string;
  created_at?: string;
  request_data?: string;
  response_data?: string;
  advertisement?: {
    id?: number;
    title?: string;
    style?: string;
    ad_type?: string;
    generated_text?: string;
    input_image_id?: number;
    input_image?: { image_url?: string };
    output_image?: { image_url?: string };
  } | null;
}

/* [v6-1] 용도(purpose) → 한글 라벨. studio 포맷 갤러리와 동일 어휘로 my-ads/detail 공용. */
export const FORMAT_LABELS: Record<string, string> = {
  sns: "이미지",
  card_news: "카드뉴스",
  banner: "배너 규격",
  detail_page: "상세페이지",
};

/* template_id(서버 형식 tpl_NN_id) → 카탈로그 표시명 역매핑.
   템플릿으로 생성한 광고는 히스토리 뱃지를 프리셋명이 아닌 템플릿 이름 그대로 표시한다. */
const TEMPLATE_NAME_BY_ID: Record<string, string> = Object.fromEntries(
  CATALOG.map((t) => [`tpl_${String(t.no).padStart(2, "0")}_${t.id}`, t.name]),
);

export function historyToCard(history: HistoryEntry): AdItem {
  const ad = history.advertisement || {};
  const outputImage = ad.output_image || {};
  let responseData: Record<string, unknown> = {};
  let requestData: Record<string, unknown> = {};
  try {
    responseData = history.response_data ? JSON.parse(history.response_data) : {};
  } catch {
    /* malformed json in history row */
  }
  try {
    requestData = history.request_data ? JSON.parse(history.request_data) : {};
  } catch {
    /* malformed json in history row */
  }
  const copy = splitCopyText(ad.generated_text || (responseData.copy_text as string) || "");
  // 템플릿으로 생성한 광고(request_data.template_id 존재)는 프리셋 뱃지 대신 템플릿 이름을
  // 표시한다. rawStyle 은 프리셋 필터용으로 원본 style 을 유지한다.
  const templateId = typeof requestData.template_id === "string" ? requestData.template_id : "";
  const templateName = templateId ? TEMPLATE_NAME_BY_ID[templateId] || "" : "";
  const style = templateName || toStyleLabel(ad.style);
  return {
    historyId: history.id,
    advertisementId: ad.id,
    emoji: "✦",
    hl: ad.title || copy.head,
    copyHead: copy.head,
    copyBody: copy.body,
    platformCopies: (responseData.platform_copies as Record<string, unknown>) || {},
    productName: ad.title || copy.head,
    style,
    rawStyle: ad.style,
    date: formatDateLabel(history.created_at),
    createdAt: history.created_at,
    inputImg: "",
    img: toAbsoluteUrl(outputImage.image_url || (responseData.image_url as string)),
    formatOutputs: Array.isArray(responseData.format_outputs)
      ? (responseData.format_outputs as string[]).map((u) => toAbsoluteUrl(u))
      : [],
    purpose: (responseData.purpose as string) || undefined,
    // [html-parity] history response_data 의 타이포 페어 매핑 (html 이식, Next 이관 시 누락)
    imageWithoutTypography: toAbsoluteUrl(responseData.image_without_typography_url as string),
    imageWithTypography: toAbsoluteUrl(responseData.image_with_typography_url as string),
    assetId: responseData.asset_id as string | undefined,
    seed: responseData.seed as number | undefined,
    adType: ad.ad_type,
    productDescription: (requestData.product_description as string) || "",
    g: "linear-gradient(150deg,#2C2140,#8A3A5A 55%,#E0912F)",
    prod: "linear-gradient(160deg,#fff6e6,#f4c988)",
  };
}

export function formatBillingDate(value?: string | null): string {
  if (!value) return "일정 미정";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "일정 미정";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).format(date);
}
export function formatBillingAmount(amount?: number, currency?: string): string {
  try {
    return new Intl.NumberFormat("ko-KR", {
      style: "currency",
      currency: currency || "KRW",
      maximumFractionDigits: 0,
    }).format(amount || 0);
  } catch {
    return `${Number(amount || 0).toLocaleString("ko-KR")}원`;
  }
}

export async function copyTextSafely(text: string) {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.focus();
  area.select();
  document.execCommand("copy");
  document.body.removeChild(area);
}

export function getDisplayName(user: AdnovaUser | null): string {
  return user?.business_name || user?.name || user?.username || "AdNova";
}
export function avatarHue(str: string): number {
  let h = 0;
  const s = str || "A";
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 360;
}
