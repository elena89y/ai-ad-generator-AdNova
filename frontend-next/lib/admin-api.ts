import { API_BASE_URL } from "@/lib/api";

const ADMIN_ACCESS_TOKEN_KEY = "admin_access_token";
const ADMIN_USER_KEY = "admin_user";

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  role: "operator" | "super_admin";
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
  return localStorage.getItem(ADMIN_ACCESS_TOKEN_KEY);
}

export function getStoredAdmin(): AdminUser | null {
  if (typeof window === "undefined") return null;

  try {
    return JSON.parse(localStorage.getItem(ADMIN_USER_KEY) || "null") as AdminUser | null;
  } catch {
    return null;
  }
}

export function storeAdminAuth(token: string, admin?: AdminUser): void {
  localStorage.setItem(ADMIN_ACCESS_TOKEN_KEY, token);
  if (admin) localStorage.setItem(ADMIN_USER_KEY, JSON.stringify(admin));
}

export function clearAdminAuth(): void {
  localStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY);
  localStorage.removeItem(ADMIN_USER_KEY);
}

export function adminPublicFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetch(buildAdminApiUrl(path), options);
}

export function adminApiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getAdminToken();
  const headers = new Headers(options.headers);

  if (token) headers.set("Authorization", `Bearer ${token}`);

  return fetch(buildAdminApiUrl(path), {
    ...options,
    headers,
  });
}
