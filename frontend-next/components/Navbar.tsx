"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "#features", label: "기능" },
  { href: "#how", label: "작동 방식" },
  { href: "#showcase", label: "예시" },
  { href: "#pricing", label: "요금" },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-all duration-300",
        scrolled ? "py-3" : "py-5"
      )}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between rounded-2xl px-5">
        <div
          className={cn(
            "flex w-full items-center justify-between rounded-2xl px-4 py-3 transition-all duration-300",
            scrolled ? "glass" : "bg-transparent"
          )}
        >
          <a href="#top" className="flex items-center gap-1.5">
            <Image
              src="/brand/brand-logo.png"
              alt="adnova-ai 로고"
              width={120}
              height={32}
              className="h-8 w-auto"
            />
            <span className="serif-accent text-xl text-accent-deep">
              studio
            </span>
          </a>

          <nav className="hidden items-center gap-8 text-sm text-muted md:flex">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
                className="transition-colors hover:text-foreground"
              >
                {l.label}
              </a>
            ))}
          </nav>

          <div className="hidden items-center gap-3 md:flex">
            <a
              href="/support"
              className="text-sm text-muted transition-colors hover:text-foreground"
            >
              고객센터
            </a>
            <a
              href="/login"
              className="text-sm text-muted transition-colors hover:text-foreground"
            >
              로그인
            </a>
            <a
              href="/signup"
              className="rounded-full accent-gradient px-4 py-2 text-sm font-semibold text-white transition-transform hover:scale-[1.03]"
            >
              무료로 시작하기
            </a>
          </div>

          <button
            onClick={() => setOpen((v) => !v)}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-border md:hidden"
            aria-label="메뉴 열기"
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {open && (
        <div className="mx-5 mt-2 rounded-2xl bg-surface border border-border p-4 shadow-xl md:hidden">
          <nav className="flex flex-col gap-4 text-sm">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="text-muted transition-colors hover:text-foreground"
              >
                {l.label}
              </a>
            ))}
            <a
              href="/support"
              onClick={() => setOpen(false)}
              className="text-muted transition-colors hover:text-foreground"
            >
              고객센터
            </a>
            <a
              href="/login"
              onClick={() => setOpen(false)}
              className="text-muted transition-colors hover:text-foreground"
            >
              로그인
            </a>
            <a
              href="/signup"
              onClick={() => setOpen(false)}
              className="mt-2 rounded-full accent-gradient px-4 py-2 text-center text-sm font-semibold text-white"
            >
              무료로 시작하기
            </a>
          </nav>
        </div>
      )}
    </header>
  );
}
