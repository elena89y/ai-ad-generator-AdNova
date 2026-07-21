"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  AdItem,
  AdnovaUser,
  AUTH_EXPIRED_EVENT,
  BillingSummary,
  GenerateResult,
  PurchaseHistory,
  apiFetch,
  clearStoredAuth,
  getStoredUser,
  getToken,
  historyToCard,
  readApiError,
  readJsonSafely,
  storeAuth,
  toAbsoluteUrl,
} from "@/lib/api";

interface StudioState {
  ready: boolean;
  user: AdnovaUser | null;
  token: string | null;
  isPremium: boolean;
  freeLeft: number;
  freeTotal: number;
  premiumLeft: number;
  premiumTotal: number;
  billingSummary: BillingSummary | null;
  billingPurchases: PurchaseHistory[];
  profileImageUrl: string | null;
  ads: AdItem[];
  dashboardSummaryText: string;
  /* 대시보드 작업 상태 (화면 이동 후에도 유지 — 프로토타입의 전역 변수 대응) */
  selectedImageId: number | null;
  selectedImageUrl: string | null;
  selectedImagePreview: string | null;
  currentResult: GenerateResult | null;
  prodName: string;
  promptText: string;
  styleLabel: string;
  useValue: string;
  /* 상세/공유 대상 */
  activeItem: AdItem | null;
  shareFrom: string;
  sharePlatform: string;

  toast: (msg: string) => void;
  setAuth: (token: string, user?: AdnovaUser | null) => void;
  clearAuth: () => void;
  refreshBilling: (showMessage?: boolean) => Promise<void>;
  refreshHistory: (showMessage?: boolean) => Promise<void>;
  refreshDashboardSummary: () => Promise<void>;
  setAds: (ads: AdItem[]) => void;
  setDashboardState: (
    patch: Partial<
      Pick<
        StudioState,
        | "selectedImageId"
        | "selectedImageUrl"
        | "selectedImagePreview"
        | "currentResult"
        | "prodName"
        | "promptText"
        | "styleLabel"
        | "useValue"
      >
    >
  ) => void;
  openDetail: (item: AdItem) => void;
  openShare: (item: AdItem, from: string, platform: string) => void;
  setBillingSummary: (summary: BillingSummary | null) => void;
  setProfileImageUrl: (imageUrl: string | null) => void;
  upgradeOpen: boolean;
  setUpgradeOpen: (open: boolean) => void;
}

const StudioContext = createContext<StudioState | null>(null);

export function useStudio(): StudioState {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("useStudio must be used within StudioProvider");
  return ctx;
}

const emptySubscribe = () => () => {};

/* SSR에서는 false, 클라이언트 하이드레이션 후 true — localStorage 접근 게이트 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false
  );
}

export default function StudioProvider({ children }: { children: React.ReactNode }) {
  const ready = useHydrated();
  /* authVersion: localStorage 인증 정보 변경(로그인/로그아웃)을 리렌더로 반영 */
  const [authVersion, setAuthVersion] = useState(0);
  const token = useMemo(() => {
    void authVersion;
    return ready ? getToken() : null;
  }, [ready, authVersion]);
  const user = useMemo<AdnovaUser | null>(() => {
    void authVersion;
    return ready ? getStoredUser() : null;
  }, [ready, authVersion]);
  const [billingSummary, setBillingSummaryState] = useState<BillingSummary | null>(null);
  const [billingPurchases, setBillingPurchases] = useState<PurchaseHistory[]>([]);
  const [profileImageUrl, setProfileImageUrl] = useState<string | null>(null);
  const [ads, setAdsState] = useState<AdItem[]>([]);
  const [dashboardSummaryText, setDashboardSummaryText] = useState("");
  const [upgradeOpen, setUpgradeOpen] = useState(false);

  const [dashState, setDashState] = useState({
    selectedImageId: null as number | null,
    selectedImageUrl: null as string | null,
    selectedImagePreview: null as string | null,
    currentResult: null as GenerateResult | null,
    prodName: "",
    promptText: "",
    styleLabel: "웜 빈티지",
    useValue: "sns",
  });
  const [activeItem, setActiveItem] = useState<AdItem | null>(null);
  const [shareFrom, setShareFrom] = useState("/studio");
  const [sharePlatform, setSharePlatform] = useState("instagram");

  const [toastMsg, setToastMsg] = useState("");
  const [toastOn, setToastOn] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const toast = useCallback((msg: string) => {
    setToastMsg(msg);
    setToastOn(true);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToastOn(false), 2200);
  }, []);

  const refreshBilling = useCallback(
    async (showMessage = false) => {
      if (!getToken()) return;
      try {
        const [summaryRes, purchasesRes] = await Promise.all([
          apiFetch("/api/billing/summary"),
          apiFetch("/api/billing/purchases?limit=50"),
        ]);
        const summary = (await readJsonSafely(summaryRes)) as BillingSummary | null;
        const purchases = await readJsonSafely(purchasesRes);
        if (!summaryRes.ok)
          throw new Error(readApiError(summary, "구독 정보를 불러오지 못했습니다"));
        if (!purchasesRes.ok)
          throw new Error(readApiError(purchases, "결제 내역을 불러오지 못했습니다"));
        setBillingSummaryState(summary);
        setBillingPurchases(Array.isArray(purchases) ? purchases : []);
      } catch (err) {
        if (showMessage)
          toast(err instanceof Error ? err.message : "결제 정보를 불러오지 못했습니다");
      }
    },
    [toast]
  );

  const refreshHistory = useCallback(
    async (showMessage = false) => {
      if (!getToken()) {
        setAdsState([]);
        return;
      }
      try {
        const res = await apiFetch("/api/history?limit=50");
        const data = await readJsonSafely(res);
        if (!res.ok)
          throw new Error(readApiError(data, "내 광고 목록을 불러오지 못했습니다"));
        const cards = ((data as unknown[]) || [])
          .filter(
            (item) =>
              (item as { advertisement?: unknown; status?: string }).advertisement &&
              (item as { status?: string }).status === "completed"
          )
          .map((item) => historyToCard(item as Parameters<typeof historyToCard>[0]));
        setAdsState(cards);
      } catch (err) {
        setAdsState([]);
        if (showMessage)
          toast(
            err instanceof Error ? err.message : "내 광고 목록을 불러오지 못했습니다"
          );
      }
    },
    [toast]
  );

  const refreshDashboardSummary = useCallback(async () => {
    if (!getToken()) return;
    try {
      const res = await apiFetch("/api/dashboard/summary?recent_limit=5");
      const data = (await readJsonSafely(res)) as {
        monthly_ad_count?: number;
        last_worked_at?: string;
      } | null;
      if (!res.ok || !data) return;
      const count = data.monthly_ad_count || 0;
      const last = data.last_worked_at
        ? new Date(data.last_worked_at)
        : null;
      const lastLabel =
        last && !Number.isNaN(last.getTime())
          ? `${last.getMonth() + 1}월 ${last.getDate()}일`
          : null;
      setDashboardSummaryText(
        lastLabel ? `이번 달 ${count}개 · 최근 ${lastLabel}` : `이번 달 ${count}개 생성`
      );
    } catch {
      /* 요약 실패는 조용히 무시 (프로토타입 동일) */
    }
  }, []);

  const setAuth = useCallback(
    (newToken: string, newUser?: AdnovaUser | null) => {
      storeAuth(newToken, newUser);
      setAuthVersion((v) => v + 1);
      refreshBilling(false);
      refreshDashboardSummary();
    },
    [refreshBilling, refreshDashboardSummary]
  );

  const clearAuth = useCallback(() => {
    clearStoredAuth();
    setAuthVersion((v) => v + 1);
    setBillingSummaryState(null);
    setBillingPurchases([]);
    setProfileImageUrl(null);
    setAdsState([]);
    setDashState((s) => ({
      ...s,
      selectedImageId: null,
      selectedImageUrl: null,
      selectedImagePreview: null,
      currentResult: null,
    }));
  }, []);

  useEffect(() => {
    const handleAuthExpired = () => clearAuth();
    window.addEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleAuthExpired);
  }, [clearAuth]);

  useEffect(() => {
    if (!ready || !token) return;

    let cancelled = false;

    async function restoreAuth() {
      try {
        const res = await apiFetch("/api/account/me");
        const data = (await readJsonSafely(res)) as AdnovaUser | null;

        if (!res.ok) {
          if (!cancelled && (res.status === 401 || res.status === 403)) {
            clearStoredAuth();
            setAuthVersion((v) => v + 1);
          }
          return;
        }

        if (!cancelled && data && token) {
          storeAuth(token, data);
          setAuthVersion((v) => v + 1);
        }
      } catch {
        // 일시적인 네트워크 오류에서는 기존 로그인 정보를 유지합니다.
      }
    }

    void restoreAuth();

    return () => {
      cancelled = true;
    };
  }, [ready, token]);

  useEffect(() => {
    if (!token) return;
    /* 마운트/로그인 직후 서버 상태 동기화 — setState는 fetch 완료 후(비동기)에만 발생 */
    queueMicrotask(() => {
      refreshBilling(false);
      refreshHistory(false);
      refreshDashboardSummary();
    });
  }, [token, refreshBilling, refreshHistory, refreshDashboardSummary]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    async function loadProfileImage() {
      try {
        const res = await apiFetch("/api/account/profile-image");
        const data = (await readJsonSafely(res)) as { image_url?: string | null } | null;
        if (!res.ok) throw new Error();
        if (!cancelled)
          setProfileImageUrl(data?.image_url ? toAbsoluteUrl(data.image_url) : null);
      } catch {
        if (!cancelled) setProfileImageUrl(null);
      }
    }

    void loadProfileImage();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const isPremium = Boolean(billingSummary?.is_premium);
  const freeLeft = billingSummary?.free_credits_remaining ?? 3;
  const freeTotal = billingSummary?.free_credit_limit ?? 3;
  const premiumLeft = billingSummary?.premium_credits_remaining ?? 0;
  const premiumTotal = billingSummary?.premium_credit_limit ?? 30;

  const value = useMemo<StudioState>(
    () => ({
      ready,
      user,
      token,
      isPremium,
      freeLeft,
      freeTotal,
      premiumLeft,
      premiumTotal,
      billingSummary,
      billingPurchases,
      profileImageUrl,
      ads,
      dashboardSummaryText,
      ...dashState,
      activeItem,
      shareFrom,
      sharePlatform,
      toast,
      setAuth,
      clearAuth,
      refreshBilling,
      refreshHistory,
      refreshDashboardSummary,
      setAds: setAdsState,
      setDashboardState: (patch) => setDashState((s) => ({ ...s, ...patch })),
      openDetail: (item) => setActiveItem(item),
      openShare: (item, from, platform) => {
        setActiveItem(item);
        setShareFrom(from);
        setSharePlatform(platform);
      },
      setBillingSummary: setBillingSummaryState,
      setProfileImageUrl,
      upgradeOpen,
      setUpgradeOpen,
    }),
    [
      ready,
      user,
      token,
      isPremium,
      freeLeft,
      freeTotal,
      premiumLeft,
      premiumTotal,
      billingSummary,
      billingPurchases,
      profileImageUrl,
      ads,
      dashboardSummaryText,
      dashState,
      activeItem,
      shareFrom,
      sharePlatform,
      toast,
      setAuth,
      clearAuth,
      refreshBilling,
      refreshHistory,
      refreshDashboardSummary,
      upgradeOpen,
    ]
  );

  return (
    <StudioContext.Provider value={value}>
      {children}
      <div className={`studio-toast${toastOn ? " on" : ""}`} role="status">
        <span className="dot" />
        <span>{toastMsg}</span>
      </div>
    </StudioContext.Provider>
  );
}
