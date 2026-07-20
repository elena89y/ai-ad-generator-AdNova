import Image from "next/image";

export default function Footer() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-10 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-1.5 text-foreground">
          <Image
            src="/brand/brand-logo.png"
            alt="adnova-ai 로고"
            width={98}
            height={26}
            className="h-[26px] w-auto"
          />
          <span className="serif-accent text-base text-accent-deep">
            studio
          </span>
        </div>
        <p>© 2026 Team AdNova · 유연정 · 김범수 · 정봄 · 한의정</p>
        <div className="flex gap-6">
          <a href="#" className="transition-colors hover:text-foreground">
            이용약관
          </a>
          <a href="#" className="transition-colors hover:text-foreground">
            개인정보처리방침
          </a>
        </div>
      </div>
    </footer>
  );
}
