import Link from "next/link";
import type { LegalSection } from "@/lib/legal-content";

type LegalPageProps = {
  title: string;
  description: string;
  sections: LegalSection[];
};

export default function LegalPage({
  title,
  description,
  sections,
}: LegalPageProps) {
  return (
    <main className="min-h-screen bg-[#101015] px-6 py-20 text-foreground">
      <div className="mx-auto max-w-3xl">
        <Link
          href="/"
          className="text-sm text-muted transition-colors hover:text-foreground"
        >
          ← AdNova Studio로 돌아가기
        </Link>

        <header className="mt-10 border-b border-white/10 pb-8">
          <h1 className="text-3xl font-bold sm:text-4xl">{title}</h1>
          <p className="mt-4 leading-7 text-muted">{description}</p>
          <p className="mt-3 text-sm text-muted">
            시행일: 2026년 7월 20일
          </p>
        </header>

        <div className="mt-10 space-y-10">
          {sections.map((section) => (
            <section key={section.title}>
              <h2 className="text-lg font-semibold">{section.title}</h2>

              <div className="mt-4 space-y-3">
                {section.paragraphs.map((paragraph) => (
                  <p
                    key={paragraph}
                    className="whitespace-pre-line text-sm leading-7 text-muted"
                  >
                    {paragraph}
                  </p>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}