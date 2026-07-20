/* 프로토타입(frontend/html/index.html)의 backend api 유틸 포팅 */

/* 기본값 "" = same-origin — next.config.ts 의 rewrites 프록시로 백엔드에 전달됨.
   별도 도메인 백엔드를 쓰려면 NEXT_PUBLIC_API_BASE_URL 설정 (백엔드 CORS 허용 필요). */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "").replace(
  /\/$/,
  ""
);

const ACCESS_TOKEN_KEY = "adnova_access_token";
const USER_KEY = "adnova_user";
const AVATAR_KEY = "adnova_avatar_photo";

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
  asset_id?: string;
  seed?: number;
  style?: string;
  image_url?: string;
  copy_text?: string;
  poster?: boolean;
  platform_copies?: Record<string, unknown>;
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
  inputImageId?: number;
  inputImg: string;
  img: string;
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
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}
export function getStoredUser(): AdnovaUser | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}
export function storeAuth(token: string, user?: AdnovaUser | null) {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
}
export function clearStoredAuth() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}
export function getStoredAvatarPhoto(): string {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem(AVATAR_KEY) || "";
  } catch {
    return "";
  }
}
export function storeAvatarPhoto(dataUrl: string) {
  try {
    localStorage.setItem(AVATAR_KEY, dataUrl);
  } catch {
    /* quota — ignore */
  }
}
export function clearAvatarPhoto() {
  localStorage.removeItem(AVATAR_KEY);
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
export async function apiFetch(path: string, options: RequestInit = {}) {
  const token = getToken();
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
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
  return `${API_BASE_URL}${url.startsWith("/") ? "" : "/"}${url}`;
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

export function historyToCard(history: HistoryEntry): AdItem {
  const ad = history.advertisement || {};
  const inputImage = ad.input_image || {};
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
  const style = toStyleLabel(ad.style);
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
    inputImageId: ad.input_image_id,
    inputImg: toAbsoluteUrl(inputImage.image_url),
    img: toAbsoluteUrl(outputImage.image_url || (responseData.image_url as string)),
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
