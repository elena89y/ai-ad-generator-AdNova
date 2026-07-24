"use client";

/* 앱바/서브바/프로필 메뉴/업그레이드 모달 — 프로토타입 공통 크롬 포팅 */

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { avatarHue, getDisplayName } from "@/lib/api";
import { useAuthenticatedImage } from "./AuthenticatedImage";
import { useHydrated, useStudio } from "./StudioProvider";

export function Brand({ large }: { large?: boolean }) {
  return (
    <Link
      href={large ? "/" : "/dashboard"}
      aria-label={large ? "AdNova 홈" : "AdNova 대시보드"}
      className={large ? "login-brand" : "brand"}
      style={{ textDecoration: "none" }}
    >
      <Image
        src="/brand/brand-logo.png"
        alt="AdNova — AI Ad Creator"
        width={large ? 150 : 113}
        height={large ? 40 : 30}
        className={large ? "brand-mark-lg" : "brand-mark"}
      />
      <span className={`studio-tag${large ? " lg" : ""}`}>studio</span>
    </Link>
  );
}

function AvatarCircle({ className, name }: { className: string; name: string }) {
  const hydrated = useHydrated();
  const { profileImageUrl } = useStudio();
  const photo = hydrated ? profileImageUrl || "" : "";
  const { displaySrc } = useAuthenticatedImage(photo);
  const initial = (name || "A").trim().charAt(0).toUpperCase();
  const hue = avatarHue(name);
  const style = displaySrc
    ? { backgroundImage: `url("${displaySrc}")`, color: "transparent" }
    : {
        background: `linear-gradient(135deg,hsl(${hue} 48% 42%),hsl(${(hue + 42) % 360} 58% 56%))`,
        color: "#fff",
      };
  return (
    <span className={className} style={style}>
      {displaySrc ? "" : initial}
    </span>
  );
}

export function ProfileMenu() {
  const { user, isPremium, freeLeft, billingReady, clearAuth } = useStudio();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const name = getDisplayName(user);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const goTo = (path: string) => {
    setOpen(false);
    router.push(path);
  };
  const logout = async () => {
    await clearAuth();
    setOpen(false);
    window.location.replace("/login?message=" + encodeURIComponent("로그아웃되었습니다."));
  };

  return (
    <div className="pf-wrap" ref={wrapRef}>
      <button
        type="button"
        aria-label="프로필 메뉴"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <AvatarCircle className="avatar" name={name} />
      </button>
      <div className={`profile-menu${open ? " on" : ""}`}>
        <div className="pf-head">
          <AvatarCircle className="av-lg" name={name} />
          <div className="info">
            <div className="nm">{name}</div>
            <div className="em">{user?.email || ""}</div>
            <span className="pf-plan">
              {!billingReady
                ? "플랜 확인 중"
                : isPremium
                  ? "프리미엄"
                  : `무료 체험 · ${freeLeft}회 남음`}
            </span>
          </div>
        </div>
        <button className="pf-item" onClick={() => goTo("/my-ads")}>
          <span className="pf-ic">🗂</span> 내 광고
        </button>
        <button className="pf-item" onClick={() => goTo("/settings")}>
          <span className="pf-ic">👤</span> 계정 설정
        </button>
        <button className="pf-item" onClick={() => goTo("/billing")}>
          <span className="pf-ic">✦</span>{" "}
          {!billingReady ? "플랜 확인 중" : isPremium ? "구독 관리" : "프리미엄 업그레이드"}
        </button>
        <button className="pf-item" onClick={() => goTo("/notices")}>
          <span className="pf-ic">📣</span> 공지사항
        </button>
        <button className="pf-item" onClick={() => goTo("/support")}>
          <span className="pf-ic">💬</span> 고객센터
        </button>
        <div className="pf-div" />
        <button className="pf-item danger" onClick={logout}>
          <span className="pf-ic">🚪</span> 로그아웃
        </button>
      </div>
    </div>
  );
}

export function UsagePill() {
  const {
    user,
    isPremium,
    freeLeft,
    freeTotal,
    premiumLeft,
    premiumTotal,
    billingReady,
    billingSummary,
  } = useStudio();
  const bonusCredits = billingSummary?.bonus_credits_remaining ?? 0;
  const purchasedCredits = billingSummary?.purchased_credits_remaining ?? 0;

  if (!user || !billingReady)
    return <div className="usage">사용량 확인 중</div>;
  return (
    <div className="usage">
      {isPremium ? (
        <>
          <span style={{ color: "var(--gold-deep)" }}>✦</span> 프리미엄{" "}
          <b>{premiumLeft}/{premiumTotal}회 남음</b>
          {bonusCredits > 0 && <> · 보너스 <b>{bonusCredits}</b></>}
          {purchasedCredits > 0 && <> · 구매 <b>{purchasedCredits}</b></>}
        </>
      ) : (
        <>
          <span className="udots">
            {Array.from({ length: freeTotal }).map((_, k) => (
              <i key={k} className={k < freeLeft ? "on" : ""} />
            ))}
          </span>
          체험 <b>{freeLeft}회 남음</b>
          {bonusCredits > 0 && <> · 보너스 <b>{bonusCredits}</b></>}
          {purchasedCredits > 0 && <> · 구매 <b>{purchasedCredits}</b></>}
        </>
      )}
    </div>
  );
}

function AccountActions({ showUsage = false }: { showUsage?: boolean }) {
  const { ready, user } = useStudio();

  if (!ready) return null;
  if (!user) {
    return (
      <Link
        href="/login"
        style={{
          display: "inline-flex",
          alignItems: "center",
          minHeight: 34,
          padding: "0 13px",
          border: "1px solid var(--line)",
          borderRadius: 9,
          color: "var(--ink)",
          fontSize: 12,
          fontWeight: 800,
          textDecoration: "none",
        }}
      >
        로그인
      </Link>
    );
  }

  return (
    <>
      {showUsage && <UsagePill />}
      <ProfileMenu />
    </>
  );
}

function PrimaryNav() {
  const pathname = usePathname();
  const inWorkspace = pathname === "/studio" || pathname === "/templates";

  return (
    <nav className="appnav">
      <Link href="/studio" className={inWorkspace ? "on" : ""}>
        ✏️ <span className="txt">광고 만들기</span>
      </Link>
      <Link href="/my-ads" className={pathname === "/my-ads" ? "on" : ""}>
        🗂 <span className="txt">내 광고</span>
      </Link>
    </nav>
  );
}

export function AppBar() {
  return (
    <div className="appbar">
      <Brand />
      <PrimaryNav />
      <div className="right">
        <AccountActions showUsage />
      </div>
    </div>
  );
}

/* 워크스페이스 좌측 내비 — 광고 이미지 / 템플릿 (모노브식 2단 구조) */
export function WorkspaceNav() {
  const pathname = usePathname();
  const items = [
    { href: "/studio", icon: "🖼", label: "광고 이미지" },
    { href: "/templates", icon: "📐", label: "템플릿" },
  ];
  return (
    <nav className="workspace-nav">
      {items.map((it) => (
        <Link key={it.href} href={it.href} className={pathname === it.href ? "on" : ""}>
          <span>{it.icon}</span> {it.label}
        </Link>
      ))}
    </nav>
  );
}

export function SubBar({
  showProfile = true,
  right,
}: {
  showProfile?: boolean;
  right?: React.ReactNode;
}) {
  return (
    <div className="subbar">
      <Brand />
      <PrimaryNav />
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
        {right}
        {showProfile && <AccountActions />}
      </div>
    </div>
  );
}

export function UpgradeModal() {
  const { upgradeOpen, setUpgradeOpen } = useStudio();
  const router = useRouter();
  return (
    <div
      className={`modal-overlay${upgradeOpen ? " on" : ""}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) setUpgradeOpen(false);
      }}
    >
      <div className="modal">
        <button className="modal-x" onClick={() => setUpgradeOpen(false)}>
          ✕
        </button>
        <div className="modal-head">
          <div className="modal-badge">✦ 업그레이드</div>
          <h3>워터마크 없이, 원본 그대로</h3>
          <p>무료 체험 3회 이후에는 크레딧으로 광고를 만들 수 있어요.</p>
        </div>
        <div className="plans">
          <div className="plan">
            <div className="plan-name">무료 체험</div>
            <div className="plan-price">₩0</div>
            <ul>
              <li>
                가입 시 <b>3회</b> 체험
              </li>
              <li className="muted">미리보기 · 로고 워터마크</li>
              <li className="muted">다운로드는 프리미엄</li>
            </ul>
            <button className="plan-btn ghost" disabled>
              현재 플랜
            </button>
          </div>
          <div className="plan hot">
            <span className="plan-tag">추천</span>
            <div className="plan-name">프리미엄</div>
            <div className="plan-price">
              ₩9,900<span>/월</span>
            </div>
            <ul>
              <li>
                매월 <b>크레딧 30회</b> 포함
              </li>
              <li>
                <b>워터마크 없음</b>
              </li>
              <li>고해상도 원본 다운로드</li>
              <li>크레딧 추가 구매 가능</li>
            </ul>
            <button
              className="plan-btn"
              onClick={() => {
                setUpgradeOpen(false);
                router.push("/checkout");
              }}
            >
              프리미엄 시작하기
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function PasswordInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="password-input">
      <input {...props} type={visible ? "text" : "password"} />
      <button
        type="button"
        className={`password-toggle${visible ? " is-visible" : ""}`}
        title={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
        aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
        onClick={() => setVisible((v) => !v)}
      >
        👁
      </button>
    </div>
  );
}

export function InfoModal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`modal-overlay${open ? " on" : ""}`}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal">
        <button className="modal-x" onClick={onClose}>
          ✕
        </button>
        <div className="modal-head">
          <h3>{title}</h3>
        </div>
        <div style={{ fontSize: 13.5, lineHeight: 1.7, color: "var(--ink-soft)" }}>
          {children}
        </div>
      </div>
    </div>
  );
}
