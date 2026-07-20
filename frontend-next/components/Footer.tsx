import Image from "next/image";
import Link from "next/link";

const productLinks = [
  { label: "주요 기능", href: "/#features" },
  { label: "작동 방식", href: "/#how-it-works" },
  { label: "요금 안내", href: "/#pricing" },
  { label: "광고 예시", href: "/#examples" },
];

const supportLinks = [
  { label: "1:1 문의", href: "/support" },
  { label: "자주 묻는 질문", href: "/faq" },
  { label: "이용 가이드", href: "/guide" },
];

const legalLinks = [
  { label: "이용약관", href: "/terms" },
  { label: "개인정보처리방침", href: "/privacy" },
  { label: "환불 및 청약철회", href: "/refund" },
];

export default function Footer() {
  return (
    <footer className="border-t border-white/10 bg-[#111116]">
      <div className="mx-auto max-w-6xl px-6 py-14">
        <div className="grid gap-12 md:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr_1fr]">
          {/* Brand */}
          <div>
            <div className="flex items-center gap-1.5">
              <Image
                src="/brand/brand-logo.png"
                alt="AdNova AI"
                width={108}
                height={28}
                className="h-7 w-auto"
              />
              <span className="serif-accent text-lg text-accent-deep">
                studio
              </span>
            </div>

            <p className="mt-5 max-w-xs text-sm leading-6 text-muted">
              상품 사진 한 장으로 빠르고 간편하게
              <br />
              광고 이미지를 제작하는 AI 서비스
            </p>
          </div>

          {/* Product */}
          <FooterColumn title="Product" links={productLinks} />

          {/* Support */}
          <FooterColumn title="Support" links={supportLinks} />

          {/* Company */}
          <div>
            <h3 className="text-sm font-semibold text-foreground">Company</h3>
            <div className="mt-5 space-y-3 text-sm text-muted">
              <p className="text-foreground">Team AdNova</p>
              <p className="leading-6">
                AI · Tech · Design
                <br />
                더 나은 광고 제작 경험을 만듭니다.
              </p>
            </div>
          </div>

          {/* Legal */}
          <FooterColumn title="Legal" links={legalLinks} />
        </div>
      </div>

      <div className="border-t border-white/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>© 2026 Team AdNova. All rights reserved.</p>
          <p>Built by Team AdNova</p>
        </div>
      </div>
    </footer>
  );
}

type FooterColumnProps = {
  title: string;
  links: {
    label: string;
    href: string;
  }[];
};

function FooterColumn({ title, links }: FooterColumnProps) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>

      <nav className="mt-5 flex flex-col gap-3">
        {links.map((link) => (
          <Link
            key={link.label}
            href={link.href}
            className="text-sm text-muted transition-colors hover:text-foreground"
          >
            {link.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}