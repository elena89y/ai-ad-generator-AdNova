"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import {
  CreditCard,
  Flag,
  KeyRound,
  LayoutDashboard,
  MailPlus,
  Megaphone,
  LogOut,
  MessageCircleQuestion,
  MessageSquareMore,
  ReceiptText,
  RotateCcw,
  ScrollText,
  ShieldCheck,
  TimerReset,
  UserCog,
  UsersRound,
} from "lucide-react";

import { useAdmin } from "@/components/admin/AdminProvider";

const navigationItems = [
  {
    href: "/admin",
    label: "대시보드",
    icon: LayoutDashboard,
  },
  {
    href: "/admin/users",
    label: "회원 관리",
    icon: UsersRound,
  },
  {
    href: "/admin/purchases",
    label: "구매 이력",
    icon: ReceiptText,
  },
  {
    href: "/admin/inquiries",
    label: "1:1 문의",
    icon: MessageSquareMore,
  },
  {
    href: "/admin/reports",
    label: "신고 관리",
    icon: Flag,
  },
  {
    href: "/admin/notices",
    label: "공지사항 관리",
    icon: Megaphone,
  },
  {
    href: "/admin/faq",
    label: "FAQ 관리",
    icon: MessageCircleQuestion,
  },
  {
    href: "/admin/subscriptions",
    label: "구독 현황",
    icon: CreditCard,
  },
  {
    href: "/admin/audit-logs",
    label: "감사 로그",
    icon: ScrollText,
  },
  {
    href: "/admin/notifications",
    label: "마케팅 알림",
    icon: MailPlus,
  },
  {
    href: "/admin/accounts",
    label: "관리자 계정",
    icon: UserCog,
  },
  {
    href: "/admin/password",
    label: "비밀번호 변경",
    icon: KeyRound,
  },
  {
    href: "/admin/security",
    label: "2단계 인증",
    icon: ShieldCheck,
  },
  {
    href: "/admin/refunds",
    label: "환불 관리",
    icon: RotateCcw,
  },
] as const;

export function AdminShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { admin, ready, signOut, extendSession } = useAdmin();
  const [sessionExtended, setSessionExtended] = useState(false);

  if (!ready || !admin) {
    return null;
  }

  async function handleSignOut() {
    await signOut();
    router.replace("/admin/login");
  }

  async function handleExtendSession() {
    const extended = await extendSession();
    if (extended) {
      setSessionExtended(true);
      return;
    }

    router.replace("/admin/login?message=" + encodeURIComponent("관리자 로그인이 만료되었습니다. 다시 로그인해 주세요."));
  }

  function isNavigationActive(href: string) {
    if (href === "/admin") {
      return pathname === "/admin";
    }

    return pathname.startsWith(href);
  }

  return (
    <div className="admin-shell min-h-screen bg-[#071426] text-[#f8fafc]">
      <div className="mx-auto flex min-h-screen max-w-[1440px]">
        <aside className="hidden w-64 shrink-0 border-r border-white/10 bg-[#0b1729]/90 px-4 py-5 lg:flex lg:flex-col">
          <Link
            href="/admin"
            className="inline-flex flex-col items-start rounded-xl px-3 py-3 transition hover:bg-white/[0.035]"
          >
            <Image
              src="/brand/brand-logo.png"
              alt="AdNova"
              width={154}
              height={42}
              priority
              className="h-auto w-[145px] object-contain"
            />

            <span className="mt-2 text-[10px] font-bold tracking-[0.16em] text-white/40">
              ADMIN CONSOLE
            </span>
          </Link>

          <nav
            className="mt-8 space-y-1"
            aria-label="관리자 메뉴"
          >
            {navigationItems.map(
              ({ href, label, icon: Icon }) => {
                const active =
                  isNavigationActive(href);

                return (
                  <Link
                    key={href}
                    href={href}
                    className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                      active
                        ? "bg-[linear-gradient(135deg,#9b7cf6_0%,#7447f2_100%)] text-white shadow-[0_8px_24px_rgba(123,80,245,0.2)]"
                        : "text-white/60 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    <Icon size={18} />
                    {label}
                  </Link>
                );
              }
            )}
          </nav>

          <div className="mt-auto border-t border-white/10 pt-4">
            <div className="rounded-xl bg-white/[0.025] px-3 py-4">
              <p className="truncate text-sm font-semibold">
                {admin.username}
              </p>

              <p className="mt-1 truncate text-xs text-white/45">
                {admin.email}
              </p>

              <span className="mt-3 inline-flex rounded-full border border-[#a78bfa]/45 px-2.5 py-1 text-[10px] font-bold tracking-wide text-[#c4b5fd]">
                {admin.role === "super_admin"
                  ? "SUPER ADMIN"
                  : "OPERATOR"}
              </span>
            </div>

            <button
              type="button"
              onClick={handleSignOut}
              className="mt-2 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-white/60 transition hover:bg-white/5 hover:text-white"
            >
              <LogOut size={18} />
              로그아웃
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <header className="flex min-h-16 items-center justify-between border-b border-white/10 px-5 lg:px-9">
            <div className="flex items-center lg:hidden">
              <Link
                href="/admin"
                aria-label="AdNova 관리자 홈"
              >
                <Image
                  src="/brand/brand-logo.png"
                  alt="AdNova"
                  width={120}
                  height={33}
                  priority
                  className="h-auto w-[110px] object-contain"
                />
              </Link>
            </div>

            <span className="hidden text-xs font-semibold tracking-[0.14em] text-white/40 lg:block">
              ADNOVA OPERATIONS
            </span>

            <div className="flex items-center gap-3">
              <span className="hidden text-sm text-white/55 sm:block">
                {admin.username}
              </span>

              <button
                type="button"
                onClick={handleExtendSession}
                className="inline-flex items-center gap-1.5 rounded-xl border border-[#a78bfa]/40 px-3 py-2 text-xs font-bold text-[#ddd6fe] transition hover:border-[#c4b5fd] hover:bg-[#a78bfa]/10"
                title="관리자 로그인 시간을 30분 연장합니다"
              >
                <TimerReset size={15} />
                <span className="hidden sm:inline">
                  {sessionExtended ? "30분 연장됨" : "세션 30분 연장"}
                </span>
              </button>

              <button
                type="button"
                onClick={handleSignOut}
                className="rounded-xl border border-white/15 px-3 py-2 text-xs font-bold text-white/70 transition hover:border-white/30 hover:bg-white/5 hover:text-white lg:hidden"
              >
                로그아웃
              </button>
            </div>
          </header>

          <nav
            className="flex gap-1.5 overflow-x-auto border-b border-white/10 px-4 py-2 lg:hidden"
            aria-label="모바일 관리자 메뉴"
          >
            {navigationItems.map(
              ({ href, label, icon: Icon }) => {
                const active =
                  isNavigationActive(href);

                return (
                  <Link
                    key={href}
                    href={href}
                    title={label}
                    aria-label={label}
                    className={`grid size-10 shrink-0 place-items-center rounded-xl transition ${
                      active
                        ? "bg-[linear-gradient(135deg,#9b7cf6_0%,#7447f2_100%)] text-white"
                        : "text-white/60 hover:bg-white/5 hover:text-white"
                    }`}
                  >
                    <Icon size={18} />
                  </Link>
                );
              }
            )}
          </nav>

          {children}
        </main>
      </div>
    </div>
  );
}
