import { API_BASE_URL } from "@/lib/api";

const ADMIN_ACCESS_TOKEN_KEY = "admin_access_token";
const ADMIN_USER_KEY = "admin_user";
const ADMIN_REFRESH_PATH = "/auth/admin-refresh";
const ADMIN_LOGOUT_PATH = "/auth/logout";
export const ADMIN_AUTH_EXPIRED_EVENT = "adnova:admin-auth-expired";

let adminRefreshPromise: Promise<string | null> | null = null;

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  role: "operator" | "super_admin";
  totp_enabled: boolean;
}

export interface AdminSummary {
  total_users: number;
  active_users: number;
  premium_users: number;
  total_advertisements: number;
  unresolved_inquiries: number;
  paid_purchase_count: number;
  paid_purchase_amount: number;
  monthly_paid_purchase_amount: number;
}

export interface ChatbotCategoryStat {
  category: string;
  count: number;
}

export interface ChatbotFaqStat {
  faq_id: string;
  count: number;
}

export interface AdminChatbotStats {
  total_chats: number;
  answered_chats: number;
  escalated_chats: number;
  rewritten_chats: number;
  escalation_rate: number;
  by_category: ChatbotCategoryStat[];
  top_cited_faqs: ChatbotFaqStat[];
}

export interface AdminFaqCandidate {
  id: number;
  source_inquiry_id: number | null;
  category: string;
  question: string;
  answer: string;
  status: "pending" | "approved" | "dismissed";
  created_at: string;
  updated_at: string;
}

export interface AdminManagedUser {
  id: number;
  username: string;
  email: string;
  name: string | null;
  business_name: string | null;
  is_active: boolean;
  created_at: string;
  plan: "free" | "premium";
  subscription_status: string | null;
}

export interface AdminUserDetail extends AdminManagedUser {
  business_type: string | null;
  updated_at: string;
  advertisement_count: number;
  bonus_credits_remaining: number;
}

export interface AdminBonusCreditGrantResult {
  user_id: number;
  bonus_credits_remaining: number;
}

export interface AdminListResponse<T> {
  total: number;
  items: T[];
}

export interface AdminPurchase {
  id: number;
  user_id: number;
  username: string;
  email: string;
  provider: string | null;
  item_type: string;
  description: string;
  amount: number;
  currency: string;
  status: string;
  purchased_at: string;
}

export type AdminInquiryStatus = "pending" | "in_progress" | "answered" | "closed";

export interface AdminInquiry {
  id: number;
  category: string;
  title: string;
  content: string;
  status: AdminInquiryStatus;
  answer: string | null;
  answered_at: string | null;
  created_at: string;
  updated_at: string;
  user_id: number;
  username: string;
  email: string;
  answered_by_admin_id: number | null;
}

export interface AdminSubscription {
  id: number;
  user_id: number;
  username: string;
  email: string;
  plan: string;
  status: string;
  provider: string | null;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  cancel_requested_at: string | null;
}

export interface AdminAuditLog {
  id: number;
  source: "admin_action" | "login_failure";
  admin_user_id: number | null;
  admin_username: string;
  action: string;
  target_type: string;
  target_id: number | null;
  detail: string | null;
  created_at: string;
}

export type AdminRole = "operator" | "super_admin";

export interface AdminAccount {
  id: number;
  user_id: number;
  username: string;
  email: string;
  name: string | null;
  role: AdminRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdminRefund {
  id: number;
  purchase_id: number;
  user_id: number;
  username: string;
  email: string;
  description: string;
  amount: number;
  reason: string;
  status: string;
  rejection_reason: string | null;
  requested_at: string;
  processed_at: string | null;
}

export interface AdminDemoRefundResult {
  purchase: AdminPurchase;
  subscription_revoked: boolean;
  purchased_credits_revoked: number;
}

function buildAdminApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const baseIncludesApi = API_BASE_URL === "/api" || API_BASE_URL.endsWith("/api");
  const pathWithoutDuplicateApi =
    baseIncludesApi && normalizedPath.startsWith("/api/")
      ? normalizedPath.slice(4)
      : normalizedPath;

  return `${API_BASE_URL}${pathWithoutDuplicateApi}`;
}

export function getAdminToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ADMIN_ACCESS_TOKEN_KEY) || sessionStorage.getItem(ADMIN_ACCESS_TOKEN_KEY);
}

export function getStoredAdmin(): AdminUser | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(
      localStorage.getItem(ADMIN_USER_KEY) || sessionStorage.getItem(ADMIN_USER_KEY) || "null"
    ) as AdminUser | null;
  } catch {
    return null;
  }
}

export function isPersistentAdminAuth(): boolean {
  return typeof window !== "undefined" && Boolean(localStorage.getItem(ADMIN_ACCESS_TOKEN_KEY));
}

export function storeAdminAuth(token: string, admin?: AdminUser, rememberMe = false): void {
  const storage = rememberMe ? localStorage : sessionStorage;
  const otherStorage = rememberMe ? sessionStorage : localStorage;
  otherStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY);
  otherStorage.removeItem(ADMIN_USER_KEY);
  storage.setItem(ADMIN_ACCESS_TOKEN_KEY, token);
  if (admin) storage.setItem(ADMIN_USER_KEY, JSON.stringify(admin));
}

export function clearAdminAuth(): void {
  localStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY);
  localStorage.removeItem(ADMIN_USER_KEY);
  sessionStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(ADMIN_USER_KEY);
}

async function readAccessToken(response: Response): Promise<string | null> {
  try {
    const data = (await response.json()) as { access_token?: string };
    return response.ok && data.access_token ? data.access_token : null;
  } catch {
    return null;
  }
}

export async function refreshAdminAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  if (!adminRefreshPromise) {
    adminRefreshPromise = fetch(buildAdminApiUrl(ADMIN_REFRESH_PATH), {
      method: "POST",
      credentials: "include",
    })
      .then(async (response) => {
        const token = await readAccessToken(response);
        if (!token) return null;
        storeAdminAuth(token, getStoredAdmin() ?? undefined, isPersistentAdminAuth());
        return token;
      })
      .catch(() => null)
      .finally(() => {
        adminRefreshPromise = null;
      });
  }
  return adminRefreshPromise;
}

export async function logoutAdminSession(): Promise<void> {
  try {
    await fetch(buildAdminApiUrl(ADMIN_LOGOUT_PATH), {
      method: "POST",
      credentials: "include",
    });
  } finally {
    clearAdminAuth();
  }
}

export function adminPublicFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetch(buildAdminApiUrl(path), { ...options, credentials: "include" });
}

async function requestAdminApi(path: string, options: RequestInit = {}, token = getAdminToken()) {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(buildAdminApiUrl(path), { ...options, headers, credentials: "include" });
}

export async function adminApiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  let response = await requestAdminApi(path, options);
  if (response.status === 401) {
    const token = await refreshAdminAccessToken();
    if (token) response = await requestAdminApi(path, options, token);
  }
  if (response.status === 401 && typeof window !== "undefined") {
    clearAdminAuth();
    window.dispatchEvent(new Event(ADMIN_AUTH_EXPIRED_EVENT));
  }
  return response;
}
