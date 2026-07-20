"use client";

/* 앱바/서브바/프로필 메뉴/업그레이드 모달 — 프로토타입 공통 크롬 포팅 */

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { avatarHue, getDisplayName } from "@/lib/api";
import { useHydrated, useStudio } from "./StudioProvider";

export function Brand({ large }: { large?: boolean }) {
  return (
    <div className={large ? "login-brand" : "brand"}>
      <Image
        src="/brand/brand-logo.png"
        alt="AdNova — AI Ad Creator"
        width={large ? 150 : 113}
        height={large ? 40 : 30}
        className={large ? "brand-mark-lg" : "brand-mark"}
      />
      <span className={`studio-tag${large ? " lg" : ""}`}>studio</span>
    </div>
  );
}

function AvatarCircle({ className, name }: { className: string; name: string }) {
  const hydrated = useHydrated();
  const { profileImageUrl } = useStudio();
  const photo = hydrated ? profileImageUrl || "" : "";
  const initial = (name || "A").trim().charAt(0).toUpperCase();
  const hue = avatarHue(name);
  const style = photo
    ? { backgroundImage: `url("${photo}")`, color: "transparent" }
    : {
        background: `linear-gradient(135deg,hsl(${hue} 48% 42%),hsl(${(hue + 42) % 360} 58% 56%))`,
        color: "#fff",
      };
  return (
    <span className={className} style={style}>
      {photo ? "" : initial}
    </span>
  );
}

export function ProfileMenu() {
  const { user, isPremium, freeLeft, clearAuth, toast } = useStudio();
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
  const logout = () => {
    clearAuth();
    setOpen(false);
    router.push("/login");
    toast("로그아웃되었습니다");
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
              {isPremium ? "프리미엄" : `무료 체험 · ${freeLeft}회 남음`}
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
          <span className="pf-ic">✦</span> 프리미엄 업그레이드
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
  const { isPremium, freeLeft, freeTotal } = useStudio();
  if (isPremium)
    return (
      <div className="usage">
        <span style={{ color: "var(--gold-deep)" }}>✦</span> 프리미엄{" "}
        <b>광고 생성 가능</b>
      </div>
    );
  return (
    <div className="usage">
      <span className="udots">
        {Array.from({ length: freeTotal }).map((_, k) => (
          <i key={k} className={k < freeLeft ? "on" : ""} />
        ))}
      </span>
      체험 <b>{freeLeft}</b>회 남음
    </div>
  );
}

export function AppBar() {
  const pathname = usePathname();
  return (
    <div className="appbar">
      <Brand />
      <nav className="appnav">
        <Link href="/studio" className={pathname === "/studio" ? "on" : ""}>
          ✏️ <span className="txt">광고 만들기</span>
        </Link>
        <Link href="/my-ads" className={pathname === "/my-ads" ? "on" : ""}>
          🗂 <span className="txt">내 광고</span>
        </Link>
      </nav>
      <div className="right">
        <UsagePill />
        <ProfileMenu />
      </div>
    </div>
  );
}

export function SubBar({
  backHref,
  backLabel,
  showProfile = true,
  right,
}: {
  backHref: string;
  backLabel: string;
  showProfile?: boolean;
  right?: React.ReactNode;
}) {
  return (
    <div className="subbar">
      <Brand />
      <Link href={backHref} className="back-link" style={{ margin: "0 0 0 6px" }}>
        ← {backLabel}
      </Link>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
        {right}
        {showProfile && <ProfileMenu />}
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
