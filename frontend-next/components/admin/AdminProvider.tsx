"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import {
  type AdminUser,
  ADMIN_AUTH_EXPIRED_EVENT,
  adminApiFetch,
  clearAdminAuth,
  extendAdminSession,
  getAdminToken,
  getStoredAdmin,
  logoutAdminSession,
  refreshAdminAccessToken,
  storeAdminAuth,
} from "@/lib/admin-api";
import { readJsonSafely } from "@/lib/api";

interface AdminContextValue {
  ready: boolean;
  admin: AdminUser | null;
  signIn: (token: string) => Promise<AdminUser>;
  signOut: () => void;
  extendSession: () => Promise<boolean>;
  refreshAdmin: () => Promise<AdminUser | null>;
}

const AdminContext = createContext<AdminContextValue | null>(null);

export function useAdmin(): AdminContextValue {
  const context = useContext(AdminContext);
  if (!context) throw new Error("useAdmin must be used within AdminProvider");
  return context;
}

export function AdminProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [admin, setAdmin] = useState<AdminUser | null>(null);

  const refreshAdmin = useCallback(async (): Promise<AdminUser | null> => {
    const existingToken = getAdminToken();
    const token = existingToken || (await refreshAdminAccessToken());
    if (!token) {
      setAdmin(null);
      return null;
    }

    try {
      const response = await adminApiFetch("/admin/me");
      const data = (await readJsonSafely(response)) as AdminUser | null;

      if (!response.ok || !data) {
        if (response.status === 401 || response.status === 403) clearAdminAuth();
        setAdmin(null);
        return null;
      }

      storeAdminAuth(token, data);
      setAdmin(data);
      return data;
    } catch {
      setAdmin(getStoredAdmin());
      return getStoredAdmin();
    }
  }, []);

  useEffect(() => {
    void refreshAdmin().finally(() => setReady(true));
  }, [refreshAdmin]);

  useEffect(() => {
    const handleAuthExpired = () => {
      clearAdminAuth();
      setAdmin(null);
      if (!window.location.pathname.startsWith("/admin/login")) {
        window.location.replace(
          "/admin/login?message=" + encodeURIComponent("관리자 로그인이 만료되었습니다. 다시 로그인해 주세요.")
        );
      }
    };
    window.addEventListener(ADMIN_AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(ADMIN_AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, []);

  const signIn = useCallback(
    async (token: string): Promise<AdminUser> => {
      storeAdminAuth(token);
      const currentAdmin = await refreshAdmin();

      if (!currentAdmin) {
        clearAdminAuth();
        throw new Error("관리자 정보를 확인하지 못했습니다.");
      }

      return currentAdmin;
    },
    [refreshAdmin]
  );

  const signOut = useCallback(() => {
    void logoutAdminSession();
    setAdmin(null);
  }, []);

  const extendSession = useCallback(async (): Promise<boolean> => {
    const token = await extendAdminSession();
    if (!token) {
      clearAdminAuth();
      setAdmin(null);
      return false;
    }

    storeAdminAuth(token, admin ?? getStoredAdmin() ?? undefined);
    return true;
  }, [admin]);

  return (
    <AdminContext.Provider value={{ ready, admin, signIn, signOut, extendSession, refreshAdmin }}>
      {children}
    </AdminContext.Provider>
  );
}
