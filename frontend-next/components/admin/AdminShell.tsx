"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  CreditCard,
  KeyRound,
  LayoutDashboard,
  LogOut,
  MessageSquareMore,
  ReceiptText,
  RotateCcw,
  ScrollText,
  ShieldCheck,
  UserCog,
  UsersRound,
} from "lucide-react";
import { useAdmin } from "@/components/admin/AdminProvider";

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { admin, ready, signOut } = useAdmin();

  if (!ready || !admin) return null;

  function handleSignOut() {
    signOut();
    router.replace("/admin/login");
  }

  const isDashboard = pathname === "/admin";
  const mobileNavigation = [
    { href: "/admin", label: "대시보드", icon: LayoutDashboard, active: isDashboard },
    { href: "/admin/users", label: "회원 관리", icon: UsersRound, active: pathname.startsWith("/admin/users") },
    { href: "/admin/purchases", label: "구매 이력", icon: ReceiptText, active: pathname.startsWith("/admin/purchases") },
    { href: "/admin/inquiries", label: "1:1 문의", icon: MessageSquareMore, active: pathname.startsWith("/admin/inquiries") },
    { href: "/admin/subscriptions", label: "구독 현황", icon: CreditCard, active: pathname.startsWith("/admin/subscriptions") },
    { href: "/admin/audit-logs", label: "감사 로그", icon: ScrollText, active: pathname.startsWith("/admin/audit-logs") },
    { href: "/admin/accounts", label: "관리자 계정", icon: UserCog, active: pathname.startsWith("/admin/accounts") },
    { href: "/admin/password", label: "비밀번호 변경", icon: KeyRound, active: pathname.startsWith("/admin/password") },
    { href: "/admin/refunds", label: "환불 관리", icon: RotateCcw, active: pathname.startsWith("/admin/refunds") },
  ];

  return (
    <div className="min-h-screen bg-[#071426] text-[#f8fafc]">
      <div className="mx-auto flex min-h-screen max-w-[1440px]">
        <aside className="hidden w-64 shrink-0 border-r border-white/10 bg-[#0b1729]/90 px-4 py-5 lg:flex lg:flex-col">
          <Link href="/admin" className="flex items-center gap-3 px-2 py-2">
            <span className="grid size-9 place-items-center rounded-lg bg-[#8b5cf6] text-white">
              <ShieldCheck size={20} strokeWidth={2.5} />
            </span>
            <span>
              <strong className="block text-sm">AdNova</strong>
              <span className="block text-xs text-white/45">Admin Console</span>
            </span>
          </Link>

          <nav className="mt-9 space-y-1">
            <Link
              href="/admin"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                isDashboard
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <LayoutDashboard size={18} />
              대시보드
            </Link>
            <Link
              href="/admin/users"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                pathname.startsWith("/admin/users")
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <UsersRound size={18} />
              회원 관리
            </Link>
            <Link
              href="/admin/purchases"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                pathname.startsWith("/admin/purchases")
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <ReceiptText size={18} />
              구매 이력
            </Link>
            <Link
              href="/admin/inquiries"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                pathname.startsWith("/admin/inquiries")
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <MessageSquareMore size={18} />
              1:1 문의
            </Link>
            <Link
              href="/admin/subscriptions"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                pathname.startsWith("/admin/subscriptions")
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <CreditCard size={18} />
              구독 현황
            </Link>
            <Link
              href="/admin/audit-logs"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                pathname.startsWith("/admin/audit-logs")
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <ScrollText size={18} />
              감사 로그
            </Link>
            <Link
              href="/admin/accounts"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                pathname.startsWith("/admin/accounts")
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <UserCog size={18} />
              관리자 계정
            </Link>
            <Link
              href="/admin/password"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                pathname.startsWith("/admin/password")
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <KeyRound size={18} />
              비밀번호 변경
            </Link>
            <Link
              href="/admin/refunds"
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition ${
                pathname.startsWith("/admin/refunds")
                  ? "bg-[#8b5cf6] text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white"
              }`}
            >
              <RotateCcw size={18} />
              환불 관리
            </Link>
          </nav>

          <div className="mt-auto border-t border-white/10 pt-4">
            <div className="px-3 pb-4">
              <p className="truncate text-sm font-semibold">{admin.username}</p>
              <p className="mt-1 truncate text-xs text-white/45">{admin.email}</p>
              <span className="mt-3 inline-flex rounded-md border border-[#a78bfa]/45 px-2 py-1 text-[11px] font-bold text-[#c4b5fd]">
                {admin.role === "super_admin" ? "SUPER ADMIN" : "OPERATOR"}
              </span>
            </div>
            <button
              type="button"
              onClick={handleSignOut}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold text-white/60 transition hover:bg-white/5 hover:text-white"
            >
              <LogOut size={18} />
              로그아웃
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <header className="flex min-h-16 items-center justify-between border-b border-white/10 px-5 lg:px-9">
            <div className="flex items-center gap-3 lg:hidden">
              <ShieldCheck size={20} className="text-[#a78bfa]" />
              <span className="text-sm font-bold">AdNova Admin</span>
            </div>
            <span className="hidden text-xs font-semibold tracking-[0.14em] text-white/40 lg:block">
              ADNOVA OPERATIONS
            </span>
            <div className="flex items-center gap-3">
              <span className="hidden text-sm text-white/55 sm:block">{admin.username}</span>
              <button
                type="button"
                onClick={handleSignOut}
                className="rounded-lg border border-white/15 px-3 py-2 text-xs font-bold text-white/70 transition hover:border-white/30 hover:text-white lg:hidden"
              >
                로그아웃
              </button>
            </div>
          </header>
          <nav className="flex gap-1 overflow-x-auto border-b border-white/10 px-4 py-2 lg:hidden" aria-label="관리자 메뉴">
            {mobileNavigation.map(({ href, label, icon: Icon, active }) => (
              <Link
                key={href}
                href={href}
                title={label}
                aria-label={label}
                className={`grid size-9 shrink-0 place-items-center rounded-lg transition ${
                  active ? "bg-[#8b5cf6] text-white" : "text-white/60 hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon size={18} />
              </Link>
            ))}
          </nav>
          {children}
        </main>
      </div>
    </div>
  );
}
