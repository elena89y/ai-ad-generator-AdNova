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
  adminApiFetch,
  clearAdminAuth,
  getAdminToken,
  getStoredAdmin,
  storeAdminAuth,
} from "@/lib/admin-api";
import { readJsonSafely } from "@/lib/api";

interface AdminContextValue {
  ready: boolean;
  admin: AdminUser | null;
  signIn: (token: string) => Promise<AdminUser>;
  signOut: () => void;
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
    const token = getAdminToken();
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
    clearAdminAuth();
    setAdmin(null);
  }, []);

  return (
    <AdminContext.Provider value={{ ready, admin, signIn, signOut, refreshAdmin }}>
      {children}
    </AdminContext.Provider>
  );
}
